"""Run boundary–population joins and save geography with explicit exclusion accounting."""

from collections.abc import Generator
from contextlib import closing
from pathlib import Path

import geopandas as gpd
import pandas as pd
from tqdm import tqdm

from capy_core.geography_types import GeographyLevel
from capy_core.pipeline_config import PipelineConfig
from capy_core.population_table_columns import GeographyColumn, PopulationColumn
from capy_core.stage_files import stage_file

from .join_population import (
    JoinColumn,
    PopulationBoundaryJoin,
    check_population_join_input,
    check_unique_identifiers,
    classify_1990_zero_population_blocks,
    join_population_to_boundaries,
    merge_1980_parent_geometries,
    repair_and_project_boundaries,
)
from .read_boundaries import BoundaryColumn, read_boundary_archive
from .repair_1980_sources import correct_richmond_population_1980, reconstruct_missing_1980_bnas
from .select_inputs import GeographyJoinInputs, select_geography_join_inputs


def join_geography_tables(config: PipelineConfig, repository_root: Path) -> pd.DataFrame:
    """Join selected boundaries to processed populations without downloading or building graphs.

    Each output state has matched GeoParquet, unmatched-population Parquet, and unmatched-boundary
    GeoParquet files, including empty tables. Reruns remove selected outputs and both run summaries
    first. Files from other selections remain; join_summary.csv is written only after all selected
    states succeed. A failed run may leave completed state files but has no completed run summary.
    Exceptions raised by ZIP, geospatial, or Parquet readers propagate unchanged.

    Args:
        config (PipelineConfig): Year/level/file selections and raw, population, and output folders.
        repository_root (Path): Base for relative configured paths.

    Returns:
        pd.DataFrame: Four population-group rows per saved state join, with year, level, state,
            group, input, matched, and unmatched population columns.

    Raises:
        OSError: A required input is missing or unreadable, or an output cannot be written.
        ValueError: Selections, folders, source identities, geometry, or population checks fail.
    """
    selections = select_geography_join_inputs(config)
    raw_data_directory = (repository_root / config.raw_data_directory).resolve()
    population_table_directory = (repository_root / config.processed_population_directory).resolve()
    joined_geography_directory = (repository_root / config.joined_geography_directory).resolve()

    for input_directory in (raw_data_directory, population_table_directory):
        if joined_geography_directory.is_relative_to(
            input_directory
        ) or input_directory.is_relative_to(joined_geography_directory):
            raise ValueError(
                "Joined geography folder must be separate from raw and population folders"
            )

    remove_selected_join_outputs(selections, joined_geography_directory)

    population_summary_tables = []
    geometry_repair_tables = []

    for selection in tqdm(selections, desc="Geography selections", unit="selection", disable=None):
        selection_summary_tables, selection_repair_tables = join_selected_geography(
            selection,
            config,
            raw_data_directory,
            population_table_directory,
            joined_geography_directory,
        )

        population_summary_tables.extend(selection_summary_tables)
        geometry_repair_tables.extend(selection_repair_tables)

    repairs_df = pd.concat(geometry_repair_tables, ignore_index=True)
    save_join_table(repairs_df, joined_geography_directory / "geometry_repairs.csv")

    population_summary_df = pd.concat(population_summary_tables, ignore_index=True)
    save_join_table(population_summary_df, joined_geography_directory / "join_summary.csv")

    return population_summary_df


def join_selected_geography(
    selection: GeographyJoinInputs,
    config: PipelineConfig,
    raw_data_directory: Path,
    population_table_directory: Path,
    joined_geography_directory: Path,
) -> tuple[list[pd.DataFrame], list[pd.DataFrame]]:
    """Join and save one year's selected resolution, processing each selected state once.

    NHGIS block extracts are read one state archive at a time. The national 1980 tract/BNA archive
    is combined with its five county supplements before parent merges and state partitioning.
    Exceptions raised by ZIP, geospatial, or Parquet readers propagate unchanged.

    Args:
        selection (GeographyJoinInputs): Boundary paths and expected population tables by state.
        config (PipelineConfig): Configured folders for TIGER 1992 supplements and original
            1990 empty-block reference tables.
        raw_data_directory (Path): Raw-data root.
        population_table_directory (Path): Root containing population Parquets.
        joined_geography_directory (Path): Separate derived-geography root.

    Returns:
        tuple[list[pd.DataFrame], list[pd.DataFrame]]: Population summary tables and geometry
            repair tables for this selection.

    Raises:
        OSError: An input or output cannot be read or written.
        ValueError: States repeat or are missing, or a geographic/population check fails.
    """
    seen_state_codes = set()
    population_summary_tables = []
    geometry_repair_tables = []

    block_reference_directory = (
        raw_data_directory / config.raw_data_subdirectories.original_1990_block_references
    )

    with (
        tqdm(
            total=len(selection.population_paths_by_state),
            desc=f"{selection.census_year} {selection.geography_level.value}",
            unit="state",
            leave=False,
            disable=None,
        ) as state_progress,
        closing(
            read_prepared_boundary_tables(
                selection,
                raw_data_directory,
                raw_data_directory / config.raw_data_subdirectories.original_1980_boundary_files,
            )
        ) as prepared_tables,
    ):
        for boundaries_df, repairs_df in prepared_tables:
            state_codes = sorted(
                set(boundaries_df[GeographyColumn.STATE_CODE])
                & set(selection.population_paths_by_state)
            )
            repeated_state_codes = seen_state_codes.intersection(state_codes)

            if repeated_state_codes:
                raise ValueError(
                    f"More than one boundary table for states {sorted(repeated_state_codes)}"
                )

            population_summary_tables.extend(
                join_and_save_boundary_states(
                    boundaries_df,
                    selection,
                    state_codes,
                    population_table_directory,
                    joined_geography_directory,
                    block_reference_directory,
                    state_progress=state_progress,
                )
            )
            seen_state_codes.update(state_codes)
            geometry_repair_tables.append(repairs_df)

    missing_state_codes = set(selection.population_paths_by_state) - seen_state_codes

    if missing_state_codes:
        raise ValueError(
            f"Selected population states lack selected boundaries: {sorted(missing_state_codes)}"
        )

    return population_summary_tables, geometry_repair_tables


def read_prepared_boundary_tables(
    selection: GeographyJoinInputs, raw_data_directory: Path, tiger_1992_directory: Path
) -> Generator[tuple[gpd.GeoDataFrame, pd.DataFrame], None, None]:
    """Read and prepare one boundary table at a time, closing each archive before the next.

    Use this iterator inside ``with closing(...)`` so an error while joining a yielded table
    also closes its source reader. National tables stay together for the 1980 supplements and
    parent merges; NHGIS block archives are read one state at a time.
    ZIP and geospatial reader exceptions propagate unchanged.

    Args:
        selection (GeographyJoinInputs): Boundary archives, expected states, year, and level.
        raw_data_directory (Path): Root of downloaded source files.
        tiger_1992_directory (Path): Configured folder for original 1980 boundary supplements.

    Yields:
        tuple[gpd.GeoDataFrame, pd.DataFrame]: Prepared boundaries and their geometry repairs.
            No population joins or output writes occur here.

    Raises:
        OSError: A source file cannot be read.
        ValueError: Source states, geometry, or historical corrections are inconsistent.
    """
    for expected_state_code, boundary_relative_path in selection.boundary_paths_by_state.items():
        with closing(
            read_boundary_archive(
                raw_data_directory / boundary_relative_path,
                boundary_relative_path,
                selection.census_year,
                selection.geography_level,
            )
        ) as boundary_tables:
            for boundaries_df in boundary_tables:
                yield prepare_selected_boundaries(
                    boundaries_df,
                    selection,
                    raw_data_directory,
                    tiger_1992_directory,
                    expected_state_code=expected_state_code,
                )


def prepare_selected_boundaries(
    boundaries_df: gpd.GeoDataFrame,
    selection: GeographyJoinInputs,
    raw_data_directory: Path,
    tiger_1992_directory: Path,
    *,
    expected_state_code: str | None,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Check source states, repair geometry, and apply the documented 1980 tract corrections.

    Supplements must have new IDs and no positive-area overlap with supplied polygons. The source
    counties have no supplied 1980 tracts; this also guards against adding a supplement twice.

    Args:
        boundaries_df (gpd.GeoDataFrame): A complete boundary table from the source reader.
        selection (GeographyJoinInputs): Census year and geography level being joined.
        raw_data_directory (Path): Base for raw source paths.
        tiger_1992_directory (Path): Configured folder for original 1980 boundary supplements.
        expected_state_code (str | None): State required by the archive filename, or None for
            a national archive. This check runs before restricting the table to selected states.

    Returns:
        tuple[gpd.GeoDataFrame, pd.DataFrame]: Valid study-coordinate polygons and individual
            buffer(0) repair accounting, restricted to selected states.

    Raises:
        OSError: A required original boundary archive cannot be read.
        ValueError: The source state, supplements, geometry repair, or parent merging fails.
    """
    if expected_state_code is not None and set(boundaries_df[GeographyColumn.STATE_CODE]) != {
        expected_state_code
    }:
        raise ValueError(f"Boundary contents disagree with state {expected_state_code}")

    boundaries_df = boundaries_df.loc[
        boundaries_df[GeographyColumn.STATE_CODE].isin(selection.population_paths_by_state)
    ].copy()

    boundaries_df, repairs_df = repair_and_project_boundaries(boundaries_df)
    boundaries_df[JoinColumn.BOUNDARY_PART_COUNT] = 1
    boundaries_df[JoinColumn.MERGED_BOUNDARY_SOURCES] = ""

    repairs_df["census_year"] = selection.census_year
    repairs_df["geography_level"] = selection.geography_level.value

    boundaries_df = prepare_1980_tract_boundaries(
        boundaries_df, selection, raw_data_directory, tiger_1992_directory
    )

    return boundaries_df, repairs_df


def prepare_1980_tract_boundaries(
    boundaries_df: gpd.GeoDataFrame,
    selection: GeographyJoinInputs,
    raw_data_directory: Path,
    tiger_1992_directory: Path,
) -> gpd.GeoDataFrame:
    """Add the missing 1980 BNAs and merge documented fragments into their population parents.

    Other selections return unchanged without reading supplements. The 1980 tract selection uses
    the complete national archive: each supplement must have a new ID and no positive-area overlap
    with supplied boundaries. The four parent merges retain the original fragment provenance.

    Args:
        boundaries_df (gpd.GeoDataFrame): Repaired study-coordinate boundaries with initial
            boundary-part counts and merge-source columns.
        selection (GeographyJoinInputs): Year and level being prepared.
        raw_data_directory (Path): Base for the supplements' saved source paths.
        tiger_1992_directory (Path): Folder containing the five original county archives.

    Returns:
        gpd.GeoDataFrame: Prepared 1980 tract/BNA boundaries, or the unchanged out-of-scope table.

    Raises:
        OSError: Reading an original county archive fails.
        BadZipFile: A supplement archive is damaged.
        ValueError: Reconstruction, geometry, overlap, identifiers, or parent merging fails.
    """
    if selection.census_year != 1980 or selection.geography_level != GeographyLevel.TRACT:
        return boundaries_df

    supplement_df = reconstruct_missing_1980_bnas(tiger_1992_directory)
    supplement_df[BoundaryColumn.SOURCE_FILE] = supplement_df[BoundaryColumn.SOURCE_FILE].map(
        lambda source_path: Path(source_path).relative_to(raw_data_directory).as_posix()
    )
    supplement_df, supplement_repairs_df = repair_and_project_boundaries(supplement_df)
    supplement_df[JoinColumn.BOUNDARY_PART_COUNT] = 1
    supplement_df[JoinColumn.MERGED_BOUNDARY_SOURCES] = ""

    if not supplement_repairs_df.empty:
        raise ValueError("Reconstructed BNA supplements must already be valid")

    for _, supplement_record in supplement_df.iterrows():
        intersecting_boundaries_df = boundaries_df.iloc[
            boundaries_df.sindex.query(supplement_record.geometry, predicate="intersects")
        ]

        if (
            intersecting_boundaries_df.geometry.intersection(supplement_record.geometry)
            .area.gt(0)
            .any()
        ):
            raise ValueError(
                f"1980 supplement overlaps supplied boundaries: {supplement_record.GEOID}"
            )

    boundaries_df = gpd.GeoDataFrame(
        pd.concat([boundaries_df, supplement_df], ignore_index=True), crs=boundaries_df.crs
    )
    check_unique_identifiers(boundaries_df, "Supplemented 1980 boundary")
    boundaries_df = merge_1980_parent_geometries(boundaries_df)

    return boundaries_df


def join_and_save_boundary_states(
    boundaries_df: gpd.GeoDataFrame,
    selection: GeographyJoinInputs,
    state_codes: list[str],
    population_table_directory: Path,
    joined_geography_directory: Path,
    block_reference_directory: Path,
    *,
    state_progress: tqdm,
) -> list[pd.DataFrame]:
    """Split a prepared boundary table by state and save each state's population join.

    Exceptions from population and reference readers propagate unchanged.

    Args:
        boundaries_df (gpd.GeoDataFrame): Prepared boundaries covering the requested states.
        selection (GeographyJoinInputs): Year, level, and population paths for the join.
        state_codes (list[str]): Selected states in processing order. The caller checks that
            none has already been processed from another boundary table.
        population_table_directory (Path): Root of processed population tables.
        joined_geography_directory (Path): Root for matched and unmatched outputs.
        block_reference_directory (Path): Original Census references for empty 1990 blocks.
        state_progress (tqdm): Selection-wide counter, advanced after each state is saved.

    Returns:
        list[pd.DataFrame]: One population summary table per saved state join.

    Raises:
        OSError: Reading or saving a state's tables fails.
        ValueError: A population or geography check fails.
    """
    population_summary_tables = []

    for state_code in state_codes:
        state_boundaries_df = boundaries_df.loc[
            boundaries_df[GeographyColumn.STATE_CODE].eq(state_code)
        ]
        summary_df = join_and_save_state(
            state_boundaries_df,
            selection,
            state_code,
            population_table_directory,
            joined_geography_directory,
            block_reference_directory,
        )
        population_summary_tables.append(summary_df)
        state_progress.update(1)

    return population_summary_tables


def join_and_save_state(
    boundaries_df: gpd.GeoDataFrame,
    selection: GeographyJoinInputs,
    state_code: str,
    population_table_directory: Path,
    joined_geography_directory: Path,
    block_reference_directory: Path,
) -> pd.DataFrame:
    """Check a state's counts, join its polygons, and save results and population accounting.

    The Richmond correction changes only derived join outputs. The processed population input
    remains an unchanged record of the source table. All four statewide totals must be preserved.

    Args:
        boundaries_df (gpd.GeoDataFrame): Valid, corrected polygons for this state.
        selection (GeographyJoinInputs): Year, level, and population paths.
        state_code (str): Two-digit state FIPS code.
        population_table_directory (Path): Root of processed population tables.
        joined_geography_directory (Path): Root of derived geography outputs.
        block_reference_directory (Path): Original STF1B/PL references, read only for 1990 blocks.

    Returns:
        pd.DataFrame: One population-accounting row for each of the four study groups.

    Raises:
        OSError: Reading or writing a table fails.
        ValueError: Input metadata, population correction, or join checks fail.
    """
    population_relative_path = selection.population_paths_by_state[state_code]
    population_df = pd.read_parquet(population_table_directory / population_relative_path)

    check_population_join_input(
        population_df, selection.census_year, selection.geography_level, state_code
    )

    original_population_totals = {
        column: int(population_df[column].sum()) for column in PopulationColumn
    }

    population_df = correct_richmond_population_1980(population_df, selection)

    for column, original_population_total in original_population_totals.items():
        if int(population_df[column].sum()) != original_population_total:
            raise ValueError(f"Population corrections changed statewide {column}")

    result = join_population_to_boundaries(
        boundaries_df, population_df, selection.census_year, selection.geography_level
    )

    result = classify_1990_zero_population_blocks(
        result, selection, state_code, block_reference_directory
    )

    matched_path, unmatched_population_path, unmatched_boundaries_path = build_join_output_paths(
        population_relative_path
    )
    output_tables = (
        (result.matched_geography_df, matched_path),
        (result.unmatched_population_df, unmatched_population_path),
        (result.unmatched_boundaries_df, unmatched_boundaries_path),
    )

    for output_df, output_path in output_tables:
        save_join_table(
            output_df.sort_values(GeographyColumn.GEOGRAPHIC_ID),
            joined_geography_directory / output_path,
        )

    return summarize_state_join(
        result,
        selection,
        state_code,
        original_population_totals,
    )


def summarize_state_join(
    result: PopulationBoundaryJoin,
    selection: GeographyJoinInputs,
    state_code: str,
    original_population_totals: dict[PopulationColumn, int],
) -> pd.DataFrame:
    """Build four population-accounting rows for one completed state join.

    Each group's input population equals its matched plus unmatched population. Groups, years,
    and geography levels overlap, so their totals must not be added together. Conservation is
    checked during corrections and joining, independently of this report.

    Args:
        result (PopulationBoundaryJoin): Matched and unmatched tables for one state.
        selection (GeographyJoinInputs): Census year and geographic resolution.
        state_code (str): Two-digit state FIPS code.
        original_population_totals (dict[PopulationColumn, int]): Statewide counts before
            corrections, for TOTPOP, WHITE, BLACK, and POC.

    Returns:
        pd.DataFrame: Year, level, state, population group, and input/matched/unmatched counts.
    """
    return pd.DataFrame(
        {
            "census_year": selection.census_year,
            "geography_level": selection.geography_level.value,
            "state_code": state_code,
            "population_group": [column.value for column in PopulationColumn],
            "input_population": [original_population_totals[column] for column in PopulationColumn],
            "matched_population": [
                int(result.matched_geography_df[column].sum()) for column in PopulationColumn
            ],
            "unmatched_population": [
                int(result.unmatched_population_df[column].sum()) for column in PopulationColumn
            ],
        }
    )


def build_join_output_paths(population_relative_path: Path) -> tuple[Path, Path, Path]:
    """Build the three output names from a processed population table's relative path.

    Args:
        population_relative_path (Path): Path beneath the population folder, such as
            2020/tracts/DE_2020_populations.parquet.

    Returns:
        tuple[Path, Path, Path]: Matched geography, unmatched population, and unmatched boundary
            paths, in that order, beneath the joined-geography folder. The year/level folders
            and state/year filename prefix are preserved. No files are created.
    """
    state_year = population_relative_path.stem.removesuffix("_populations")

    return (
        population_relative_path.with_name(f"{state_year}_geography.parquet"),
        population_relative_path.with_name(f"{state_year}_unmatched_population.parquet"),
        population_relative_path.with_name(f"{state_year}_unmatched_boundaries.parquet"),
    )


def save_join_table(records_df: pd.DataFrame, output_path: Path) -> None:
    """Write a Parquet/GeoParquet table or CSV accounting file through a temporary filename.

    Args:
        records_df (pd.DataFrame): Population records, geographic records with CRS, or accounting.
        output_path (Path): Final .parquet or .csv filename in the derived-geography directory.

    Raises:
        OSError: Writing or renaming fails; the temporary file is removed.
        ValueError: The table cannot be serialized or the output extension is unsupported.
    """
    with stage_file(output_path.parent) as temporary_path:
        if output_path.suffix == ".csv":
            records_df.to_csv(temporary_path, index=False, lineterminator="\n")
        elif output_path.suffix == ".parquet":
            records_df.to_parquet(temporary_path, compression="zstd", index=False)
        else:
            raise ValueError(f"Unsupported join output extension: {output_path.suffix}")

        temporary_path.replace(output_path)


def remove_selected_join_outputs(
    selections: list[GeographyJoinInputs], joined_geography_directory: Path
) -> None:
    """Remove selected derived files and both run summaries before rebuilding the joins.

    All output paths are checked before any file is removed. Missing files are allowed, and
    outputs for unselected states, years, and levels remain in place.

    Args:
        selections (list[GeographyJoinInputs]): Selected population tables that determine the
            matched and unmatched output filenames.
        joined_geography_directory (Path): Resolved, absolute root for joined outputs, already
            checked by the caller to be separate from the input folders.

    Raises:
        ValueError: An output path resolves outside the configured output folder.
        OSError: Resolving or removing an output path fails.
    """
    output_paths = [
        joined_geography_directory / "join_summary.csv",
        joined_geography_directory / "geometry_repairs.csv",
    ]

    for selection in selections:
        for population_relative_path in selection.population_paths_by_state.values():
            output_paths.extend(
                joined_geography_directory / path
                for path in build_join_output_paths(population_relative_path)
            )

    if any(not path.resolve().is_relative_to(joined_geography_directory) for path in output_paths):
        raise ValueError("A join output resolves outside its configured directory")

    for output_path in output_paths:
        output_path.unlink(missing_ok=True)
