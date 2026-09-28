"""Build connected graphs from saved memberships and publish complete year/resolution archives."""

from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from multiprocessing import get_context
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd
from tqdm import tqdm

from capy_core.assign_study_areas.assign_units import MembershipStatus
from capy_core.assign_study_areas.study_area_columns import MembershipColumn, StudyAreaColumn
from capy_core.data_directories import resolve_separate_output_directory
from capy_core.join_geographies.select_inputs import (
    GeographyJoinInputs,
    select_geography_join_inputs,
)
from capy_core.pipeline_config import PipelineConfig
from capy_core.population_table_columns import PopulationColumn
from capy_core.retrieve_data.prepare_file_requests import build_geography_requests
from capy_core.stage_files import stage_file

from .build_area_graph import AreaGraphFiles, AreaGraphInputs, build_and_save_area_graph
from .graph_archives import build_zip_member, write_file_to_archive
from .read_inputs import read_selection_memberships, read_study_area_definitions


def build_graph_archives(config: PipelineConfig, repository_root: Path) -> pd.DataFrame:
    """Build one ZIP per selected Census year and level, containing connected graphs and accounting.

    Reruns remove the named archives and completion summary for this area type/vintage before
    reading inputs. Each archive is published only after all its areas succeed. The run summary
    is written last; an interrupted run can leave completed archives but no completion summary.
    Graph workers read polygons and save area files independently. One process assembles each ZIP
    in stable area order. Download worker settings do not control this stage.

    Args:
        config (PipelineConfig): Node selections, study-area settings, and input/output folders.
        repository_root (Path): Base for relative configured folders.

    Returns:
        pd.DataFrame: One outcome per study area, year, and level, with population accounting.

    Raises:
        OSError: Inputs cannot be read or outputs cannot be written.
        ValueError: Paths overlap inputs, selected memberships are absent/inconsistent, or a
            graph fails population or connection checks. Library-specific errors propagate.
    """
    raw_data_directory = (repository_root / config.raw_data_directory).resolve()
    population_table_directory = (repository_root / config.processed_population_directory).resolve()
    joined_geography_directory = (repository_root / config.joined_geography_directory).resolve()
    study_area_root = (repository_root / config.study_area_directory).resolve()
    input_directories = (
        raw_data_directory,
        population_table_directory,
        joined_geography_directory,
        study_area_root,
    )
    graph_archive_directory = resolve_separate_output_directory(
        repository_root, config.graph_archive_directory, input_directories
    )
    study_area_directory = (
        study_area_root / config.study_area_type.value / str(config.study_area_vintage)
    )
    archive_prefix = f"{config.study_area_type}_{config.study_area_vintage}"
    summary_path = graph_archive_directory / f"{archive_prefix}_summary.parquet"
    summary_path.unlink(missing_ok=True)

    for previous_archive in graph_archive_directory.glob(f"{archive_prefix}_*.zip"):
        previous_archive.unlink()

    definitions_df = read_study_area_definitions(study_area_directory, config).to_crs("ESRI:102003")
    selected_geography_inputs = select_geography_join_inputs(config)
    graph_node_inputs = [
        geography_inputs
        for geography_inputs in selected_geography_inputs
        if geography_inputs.census_year in config.census_geography_years
        and geography_inputs.geography_level in config.census_geography_levels
    ]
    expected_years_and_levels = {
        (request.census_year, request.geography_level)
        for request in build_geography_requests(config)
        if request.census_year in config.census_geography_years
        and request.geography_level in config.census_geography_levels
    }

    if {
        (inputs.census_year, inputs.geography_level) for inputs in graph_node_inputs
    } != expected_years_and_levels:
        raise ValueError("Filename filters omit configured graph-node selections")

    summary_tables = []

    for geography_inputs in graph_node_inputs:
        archive_path = graph_archive_directory / (
            f"{archive_prefix}_{geography_inputs.census_year}_{geography_inputs.geography_level}.zip"
        )
        summary_tables.append(
            build_selection_archive(
                archive_path,
                definitions_df,
                geography_inputs,
                study_area_directory,
                joined_geography_directory,
                config.max_parallel_graphs,
                warn_on_polygon_overlaps=config.warn_on_polygon_overlaps,
            )
        )

    summary_df = pd.concat(summary_tables, ignore_index=True)

    with stage_file(graph_archive_directory) as temporary_path:
        summary_df.to_parquet(temporary_path, index=False)
        temporary_path.replace(summary_path)

    return summary_df


def build_selection_archive(
    archive_path: Path,
    definitions_df: gpd.GeoDataFrame,
    geography_inputs: GeographyJoinInputs,
    study_area_directory: Path,
    joined_geography_directory: Path,
    max_parallel_graphs: int,
    *,
    warn_on_polygon_overlaps: bool = True,
) -> pd.DataFrame:
    """Publish one complete year/level archive with graph JSONs, removed units, and accounting.

    Args:
        archive_path (Path): Final ZIP filename, replaced only after successful writing.
        definitions_df (gpd.GeoDataFrame): All configured study-area definitions.
        geography_inputs (GeographyJoinInputs): Node year/level and expected source paths.
        study_area_directory (Path): Definitions and membership output directory.
        joined_geography_directory (Path): Root for matched population polygons.
        max_parallel_graphs (int): Maximum concurrent area builds; 1 runs in the main process.
        warn_on_polygon_overlaps (bool): Report overlaps above 100 mm²; defaults to True.
            False suppresses overlap warnings only, in both serial and parallel construction.

    Returns:
        pd.DataFrame: Archive inventory and population accounting, also saved as summary.csv.

    Raises:
        OSError: Reading inputs or writing the archive fails.
        ValueError: Memberships, populations, polygons, or graph connections fail validation.
    """
    memberships_df, assignment_summary_df = read_selection_memberships(
        study_area_directory, definitions_df, geography_inputs, joined_geography_directory
    )
    area_inputs = iter_area_graph_inputs(definitions_df, assignment_summary_df, memberships_df)
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix=".graph-build-", dir=archive_path.parent) as temporary_name:
        temporary_directory = Path(temporary_name)
        (temporary_directory / "graphs").mkdir()
        (temporary_directory / "removed_units").mkdir()
        area_files = build_area_graph_files(
            area_inputs,
            len(definitions_df),
            geography_inputs,
            joined_geography_directory,
            temporary_directory,
            max_parallel_graphs,
            warn_on_polygon_overlaps=warn_on_polygon_overlaps,
        )

        return publish_selection_archive(archive_path, area_files, temporary_directory)


def publish_selection_archive(
    archive_path: Path, area_files: list[AreaGraphFiles], temporary_directory: Path
) -> pd.DataFrame:
    """Assemble completed area files in stable order and publish their ZIP and internal summary.

    Args:
        archive_path (Path): Final filename, replaced only after the ZIP closes successfully.
        area_files (list[AreaGraphFiles]): Complete worker results in study-area ID order.
        temporary_directory (Path): Selection-owned folder containing the saved member files.

    Returns:
        pd.DataFrame: Archive inventory and population accounting, also stored as summary.csv.

    Raises:
        OSError: Reading files or writing/publishing the ZIP fails.
    """
    summary_rows = [area.summary for area in area_files]

    with stage_file(archive_path.parent) as temporary_path:
        with ZipFile(temporary_path, "w") as archive:
            for area in tqdm(
                area_files, desc=f"Saving {archive_path.stem}", unit="area", disable=None
            ):
                for member_path in area.member_paths:
                    write_file_to_archive(archive, member_path, temporary_directory)

            summary_df = pd.DataFrame(summary_rows)
            summary_df["archive"] = archive_path.name
            count_columns = [
                "node_count",
                "edge_count",
                "input_unit_count",
                "removed_unit_count",
                "initial_component_count",
                "artificial_edge_count",
                *(
                    f"{group}_{column}"
                    for group in ("input", "retained", "removed")
                    for column in PopulationColumn
                ),
            ]
            summary_df[count_columns] = summary_df[count_columns].astype("Int64")
            archive.writestr(build_zip_member("summary.csv"), summary_df.to_csv(index=False))

        temporary_path.replace(archive_path)

    return summary_df


def iter_area_graph_inputs(
    definitions_df: gpd.GeoDataFrame,
    assignment_summary_df: pd.DataFrame,
    memberships_df: pd.DataFrame,
) -> Iterator[AreaGraphInputs]:
    """Prepare one area's inputs at a time, starting with the largest membership counts.

    Larger areas start first so expensive block graphs are less likely to be left until the end.
    Geometry is omitted from the area metadata; workers read the selected unit polygons directly.

    Args:
        definitions_df (gpd.GeoDataFrame): Validated area definitions in stable ID order.
        assignment_summary_df (pd.DataFrame): Validated assignment counts indexed by area ID.
        memberships_df (pd.DataFrame): Validated membership rows for this year and level.

    Yields:
        AreaGraphInputs: One area's metadata, assignment, and membership subset. Inputs are unchanged.
    """
    definitions_by_id_df = definitions_df.drop(columns="geometry").set_index(
        StudyAreaColumn.STUDY_AREA_ID, drop=False
    )
    memberships_by_area = memberships_df.groupby(StudyAreaColumn.STUDY_AREA_ID)
    assignments_by_size_df = assignment_summary_df.sort_values(
        MembershipColumn.UNIT_COUNT, ascending=False, kind="stable", na_position="last"
    )

    for area_id in assignments_by_size_df.index:
        assignment = assignment_summary_df.loc[area_id]
        area_memberships_df = memberships_df.iloc[:0]

        if assignment[MembershipColumn.STATUS] == MembershipStatus.READY:
            area_memberships_df = pd.DataFrame(memberships_by_area.get_group(area_id))

        yield AreaGraphInputs(definitions_by_id_df.loc[area_id], assignment, area_memberships_df)


def build_area_graph_files(
    area_inputs: Iterator[AreaGraphInputs],
    area_count: int,
    geography_inputs: GeographyJoinInputs,
    joined_geography_directory: Path,
    temporary_directory: Path,
    max_parallel_graphs: int,
    *,
    warn_on_polygon_overlaps: bool = True,
) -> list[AreaGraphFiles]:
    """Build and save area files with at most one submitted task per worker.

    Workers own their individual JSON/CSV writes; the caller owns the temporary directory and
    final ZIP. Results contain paths and scalar accounting, never graphs or polygon tables.
    On failure or interruption, queued work is cancelled and running workers finish before the
    caller cleans up. Progress counts finished area builds, not submission order.

    Args:
        area_inputs (Iterator[AreaGraphInputs]): Area inputs, usually largest first.
        area_count (int): Number of areas for progress reporting and the worker limit.
        geography_inputs (GeographyJoinInputs): Expected node year and level.
        joined_geography_directory (Path): Root of the population polygons.
        temporary_directory (Path): Existing selection-owned graphs/ and removed_units/ folders.
        max_parallel_graphs (int): Positive worker limit. Use 1 to avoid subprocesses.
        warn_on_polygon_overlaps (bool): Report overlaps above 100 mm²; defaults to True.
            Passed to each build without changing its graph or population checks.

    Returns:
        list[AreaGraphFiles]: Completed results sorted by area ID for deterministic ZIP assembly.

    Raises:
        OSError: A worker cannot read inputs or save its files.
        ValueError: A worker detects invalid input or graph accounting. Worker exceptions propagate.
    """
    description = f"{geography_inputs.census_year} {geography_inputs.geography_level} graphs"

    with tqdm(total=area_count, desc=description, unit="area", disable=None) as progress:
        if max_parallel_graphs == 1:
            area_files = []

            for area in area_inputs:
                area_files.append(
                    build_and_save_area_graph(
                        area,
                        geography_inputs,
                        joined_geography_directory,
                        temporary_directory,
                        warn_on_polygon_overlaps=warn_on_polygon_overlaps,
                    )
                )
                progress.update(1)
        else:
            area_files = build_area_graph_files_in_parallel(
                area_inputs,
                geography_inputs,
                joined_geography_directory,
                temporary_directory,
                min(max_parallel_graphs, area_count),
                progress,
                warn_on_polygon_overlaps=warn_on_polygon_overlaps,
            )

    return sorted(area_files, key=lambda area: str(area.summary[StudyAreaColumn.STUDY_AREA_ID]))


def build_area_graph_files_in_parallel(
    area_inputs: Iterator[AreaGraphInputs],
    geography_inputs: GeographyJoinInputs,
    joined_geography_directory: Path,
    temporary_directory: Path,
    worker_count: int,
    progress: tqdm,
    *,
    warn_on_polygon_overlaps: bool = True,
) -> list[AreaGraphFiles]:
    """Keep graph workers occupied without queuing every area's membership table in memory.

    This function owns the pool. It cancels queued tasks and waits for running tasks on every
    exit, so the selection's temporary directory can be removed safely by its caller.

    Args:
        area_inputs (Iterator[AreaGraphInputs]): Area inputs prepared as worker slots become free.
        geography_inputs (GeographyJoinInputs): Expected node year and level.
        joined_geography_directory (Path): Population-polygon input root.
        temporary_directory (Path): Selection-owned folder for workers' distinct output files.
        worker_count (int): Positive process limit, capped at the number of study areas.
        progress (tqdm): Parent-owned counter updated when a worker result is received.
        warn_on_polygon_overlaps (bool): Report overlaps above 100 mm²; defaults to True.
            Applied inside each worker, independently of the parent process's warning filters.

    Returns:
        list[AreaGraphFiles]: Completed area files and accounting in completion order.

    Raises:
        OSError: A worker cannot read or write files.
        ValueError: A worker rejects invalid data. Other worker exceptions also propagate.
    """
    area_files = []
    pending = set()
    pool = ProcessPoolExecutor(max_workers=worker_count, mp_context=get_context("spawn"))

    try:
        while True:
            while len(pending) < worker_count:
                area = next(area_inputs, None)

                if area is None:
                    break

                pending.add(
                    pool.submit(
                        build_and_save_area_graph,
                        area,
                        geography_inputs,
                        joined_geography_directory,
                        temporary_directory,
                        warn_on_polygon_overlaps=warn_on_polygon_overlaps,
                    )
                )

            if not pending:
                break

            completed, pending = wait(pending, return_when=FIRST_COMPLETED)

            for future in completed:
                area_files.append(future.result())
                progress.update(1)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)

    return area_files
