"""Build connected graphs from saved memberships and publish complete year/resolution archives."""

import json
from enum import StrEnum
from pathlib import Path
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

from .construct_graph import build_connected_graph
from .graph_archives import build_zip_member, write_graph_to_archive
from .read_inputs import read_area_polygons, read_selection_memberships, read_study_area_definitions


class GraphStatus(StrEnum):
    """Whether a graph exists or why an area has no graph member."""

    READY = "ready"
    NO_UNITS_SELECTED = "no_units_selected"
    NO_UNITS_AFTER_POPULATION_FILTER = "no_units_after_population_filter"
    HISTORICAL_COVERAGE_UNAVAILABLE = "historical_coverage_unavailable"


def build_graph_archives(config: PipelineConfig, repository_root: Path) -> pd.DataFrame:
    """Build one ZIP per selected Census year and level, containing connected graphs and accounting.

    Reruns remove the named archives and completion summary for this area type/vintage before
    reading inputs. Each archive is published only after all its areas succeed. The run summary
    is written last; an interrupted run can leave completed archives but no completion summary.
    Graphs are built one area at a time, independently of download worker settings.

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
) -> pd.DataFrame:
    """Publish one complete year/level archive with graph JSONs, removed units, and accounting.

    Args:
        archive_path (Path): Final ZIP filename, replaced only after successful writing.
        definitions_df (gpd.GeoDataFrame): All configured study-area definitions.
        geography_inputs (GeographyJoinInputs): Node year/level and expected source paths.
        study_area_directory (Path): Definitions and membership output directory.
        joined_geography_directory (Path): Root for matched population polygons.

    Returns:
        pd.DataFrame: Archive inventory and population accounting, also saved as summary.csv.

    Raises:
        OSError: Reading inputs or writing the archive fails.
        ValueError: Memberships, populations, polygons, or graph connections fail validation.
    """
    memberships_df, assignment_summary_df = read_selection_memberships(
        study_area_directory, definitions_df, geography_inputs, joined_geography_directory
    )
    memberships_by_area = memberships_df.groupby(StudyAreaColumn.STUDY_AREA_ID)
    summary_rows = []

    with stage_file(archive_path.parent) as temporary_path:
        with ZipFile(temporary_path, "w") as archive:
            for _, definition in tqdm(
                definitions_df.iterrows(),
                total=len(definitions_df),
                desc=f"{geography_inputs.census_year} {geography_inputs.geography_level} graphs",
                unit="area",
                disable=None,
            ):
                area_id = definition[StudyAreaColumn.STUDY_AREA_ID]
                assignment = assignment_summary_df.loc[area_id]
                area_memberships_df = memberships_df.iloc[:0]

                if assignment[MembershipColumn.STATUS] == MembershipStatus.READY:
                    area_memberships_df = pd.DataFrame(memberships_by_area.get_group(area_id))

                summary_rows.append(
                    build_and_write_area_graph(
                        archive,
                        definition,
                        assignment,
                        area_memberships_df,
                        geography_inputs,
                        joined_geography_directory,
                        archive_path.parent,
                    )
                )

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


def build_and_write_area_graph(
    archive: ZipFile,
    definition: pd.Series,
    assignment: pd.Series,
    area_memberships_df: pd.DataFrame,
    geography_inputs: GeographyJoinInputs,
    joined_geography_directory: Path,
    temporary_directory: Path,
) -> dict[str, str | int | None]:
    """Write one area's graph and removed units, or record why no graph is available.

    Args:
        archive (ZipFile): Open destination archive, owned by build_selection_archive.
        definition (pd.Series): Area metadata and boundary.
        assignment (pd.Series): Validated membership status and totals for this area.
        area_memberships_df (pd.DataFrame): Saved memberships, empty for areas with no selected
            units or unsupported historical coverage.
        geography_inputs (GeographyJoinInputs): Expected node year and level.
        joined_geography_directory (Path): Joined population-polygon root.
        temporary_directory (Path): Directory for GerryChain's disposable JSON file.

    Returns:
        dict: Scalar archive-summary fields. A fully filtered area has no graph member but keeps
            its removed-unit file and population accounting.

    Raises:
        OSError: Reading or writing fails.
        ValueError: Joined inputs disagree with memberships, or graph construction fails.
    """
    area_id = definition[StudyAreaColumn.STUDY_AREA_ID]
    status = GraphStatus(assignment[MembershipColumn.STATUS])
    absent_count = None if status == GraphStatus.HISTORICAL_COVERAGE_UNAVAILABLE else 0
    summary = {
        StudyAreaColumn.STUDY_AREA_ID: area_id,
        MembershipColumn.CENSUS_YEAR: geography_inputs.census_year,
        MembershipColumn.GEOGRAPHY_LEVEL: geography_inputs.geography_level.value,
        MembershipColumn.STATUS: status,
        "graph_member": None,
        "node_count": absent_count,
        "edge_count": absent_count,
        "input_unit_count": absent_count,
        "removed_unit_count": absent_count,
        "initial_component_count": absent_count,
        "artificial_edge_count": absent_count,
    }

    for population_group in ("input", "retained", "removed"):
        for population_column in PopulationColumn:
            summary[f"{population_group}_{population_column}"] = absent_count

    if status != GraphStatus.READY:
        return summary

    units_df = read_area_polygons(area_memberships_df, geography_inputs, joined_geography_directory)
    graph, removed_units_df = build_connected_graph(units_df)
    area_metadata = json.loads(str(definition.drop(labels="geometry").to_json()))
    graph.graph.update(area_metadata)
    graph.graph[MembershipColumn.CENSUS_YEAR] = geography_inputs.census_year
    graph.graph[MembershipColumn.GEOGRAPHY_LEVEL] = geography_inputs.geography_level.value
    graph_member = f"graphs/{area_id}.json" if graph else None

    if graph_member is not None:
        write_graph_to_archive(archive, graph_member, graph, temporary_directory)

    archive.writestr(
        build_zip_member(f"removed_units/{area_id}.csv"), removed_units_df.to_csv(index=False)
    )
    summary.update(
        {
            MembershipColumn.STATUS: GraphStatus.READY
            if graph
            else GraphStatus.NO_UNITS_AFTER_POPULATION_FILTER,
            "graph_member": graph_member,
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
        }
    )

    for field in (
        "input_unit_count",
        "removed_unit_count",
        "initial_component_count",
        "artificial_edge_count",
    ):
        summary[field] = graph.graph[field]

    for population_group in ("input", "retained", "removed"):
        for population_column in PopulationColumn:
            summary[f"{population_group}_{population_column}"] = graph.graph[
                f"{population_group}_population"
            ][population_column]

    return summary
