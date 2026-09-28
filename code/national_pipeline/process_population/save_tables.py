"""Plan and save processed population tables and their row/population accounting."""

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

import pandas as pd

from national_pipeline.derived_file_paths import build_population_output_path
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.population_table_columns import PopulationColumn
from national_pipeline.retrieve_data.raw_file_requests import (
    CensusFileRequest,
    NhgisTableFileRequest,
)
from national_pipeline.retrieve_data.state_codes import STATE_FIPS_CODES
from national_pipeline.stage_files import stage_file

from .read_nhgis import describe_nhgis_population_request


class PopulationComparison(StrEnum):
    """Population checks applied to a table, with text values saved in processing_summary.csv."""

    CENSUS_COUNTS_MATCH_STATE = "all_11_counts_match_state"
    PLACES_DO_NOT_PARTITION_STATE = "not_applicable_places_do_not_partition_state"
    RESIDENT_TOTALS_MATCH_PUBLISHED = "resident_totals_match_published_reference"
    STUDY_COUNTS_MATCH_PUBLISHED = "study_counts_match_published_state_reference"
    PARTIAL_1980_TRACT_COVERAGE = "partial_1980_tract_coverage_bounded_by_state"
    NHGIS_COUNTS_MATCH_STATE = "all_source_and_study_counts_match_state"


@dataclass(frozen=True)
class PopulationTableSummary:
    """Accounting for one saved population table, including which total comparison was applied.

    Counts describe this table only. Do not add totals across levels or years because they
    describe overlapping populations. input_rows equals output_rows; no records are filtered.
    """

    source_file: str
    output_file: str
    input_rows: int
    output_rows: int
    total_population: int
    white_population: int
    black_population: int
    poc_population: int
    comparison: PopulationComparison


def build_population_output_paths(
    census_requests: list[CensusFileRequest], nhgis_requests: list[NhgisTableFileRequest]
) -> dict[tuple[int, GeographyLevel], dict[str | None, Path]]:
    """Describe the population outputs for selected inputs, grouped by year, level, and state.

    Modern inputs each produce one table. A historical substate archive produces one table for
    each of the 50 states and DC. National state-reference tables use the None state key.
    Cleanup and downstream joins use these same descriptions; no source files are read here.

    Args:
        census_requests (list[CensusFileRequest]): Modern population inputs and state references.
        nhgis_requests (list[NhgisTableFileRequest]): Historical population archives and references.

    Returns:
        dict[tuple[int, GeographyLevel], dict[str | None, Path]]: Paths beneath the configured
            population output folder, indexed by year/level and then state.

    Raises:
        ValueError: An NHGIS request is unsupported or a state has no postal abbreviation.
    """
    output_paths_by_year_and_level: dict[tuple[int, GeographyLevel], dict[str | None, Path]] = {}

    for request in census_requests:
        year_and_level = (request.census_year, request.geography_level)
        state_paths = output_paths_by_year_and_level.setdefault(year_and_level, {})
        output_path = build_population_output_path(
            request.census_year, request.geography_level, request.state_code
        )
        state_paths[request.state_code] = output_path

    for request in nhgis_requests:
        census_year, geography_level = describe_nhgis_population_request(request)
        state_codes = (
            (None,)
            if geography_level == GeographyLevel.STATE
            else tuple(state_code for state_code in STATE_FIPS_CODES if state_code != "72")
        )
        output_paths_by_year_and_level[census_year, geography_level] = {
            state_code: build_population_output_path(census_year, geography_level, state_code)
            for state_code in state_codes
        }

    return output_paths_by_year_and_level


def save_population_parquet(population_df: pd.DataFrame, population_output_path: Path) -> None:
    """Save a compressed population table, preserving string IDs and integer counts.

    Pandas writes directly to a temporary file while processing one state's table at a time.
    The final filename appears only after serialization and writing both succeed.

    Args:
        population_df (pd.DataFrame): Checked population records, including their source columns.
        population_output_path (Path): Derived output filename, outside the raw-data directory.

    Raises:
        OSError: Writing or renaming the output fails; temporary files are removed.
        ValueError: A column cannot be represented in Parquet.
        OverflowError: An integer exceeds the supported storage range.
    """
    with stage_file(population_output_path.parent) as temporary_path:
        population_df.to_parquet(temporary_path, engine="pyarrow", compression="zstd", index=False)
        temporary_path.replace(population_output_path)


def save_population_summary(
    summaries: list[PopulationTableSummary], summary_output_path: Path
) -> None:
    """Save this run's small accounting table as CSV after all population tables succeed.

    Args:
        summaries (list[PopulationTableSummary]): Input/output names, row counts, and totals.
        summary_output_path (Path): Summary filename beneath the processed population folder.

    Raises:
        OSError: Writing or renaming the summary fails; temporary files are removed.
    """
    summary_df = pd.DataFrame([asdict(summary) for summary in summaries])

    with stage_file(summary_output_path.parent) as temporary_path:
        summary_df.to_csv(temporary_path, index=False, lineterminator="\n", encoding="utf-8")
        temporary_path.replace(summary_output_path)


def summarize_population_table(
    population_df: pd.DataFrame,
    source_file: str,
    output_path: Path,
    comparison: PopulationComparison,
) -> PopulationTableSummary:
    """Build the row and population accounting for one processed table.

    Population processing retains every source row, so both input_rows and output_rows use
    this table's length. Call after saving the table; this function calculates totals without
    reading the saved file or repeating the population comparison.

    Args:
        population_df (pd.DataFrame): Checked records with integer TOTPOP, WHITE, BLACK, and POC
            counts. All source rows must still be present.
        source_file (str): Source filename relative to the configured raw-data directory.
        output_path (Path): Saved table path relative to the processed-population directory.
        comparison (PopulationComparison): Check already applied to this table, or the label
            indicating that places do not partition a state.

    Returns:
        PopulationTableSummary: File locations, equal input/output row counts, study population
            totals, and the comparison label for one row of processing_summary.csv.

    Raises:
        KeyError: A required population column is missing.
    """
    return PopulationTableSummary(
        source_file=source_file,
        output_file=output_path.as_posix(),
        input_rows=len(population_df),
        output_rows=len(population_df),
        total_population=int(population_df[PopulationColumn.TOTAL].sum()),
        white_population=int(population_df[PopulationColumn.NON_HISPANIC_WHITE].sum()),
        black_population=int(population_df[PopulationColumn.NON_HISPANIC_BLACK].sum()),
        poc_population=int(population_df[PopulationColumn.POC].sum()),
        comparison=comparison,
    )
