"""Name and save processed population tables and their row/population accounting."""

from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

import pandas as pd
import us

from capy_core.geography_types import GeographyLevel
from capy_core.population_table_columns import PopulationColumn
from capy_core.stage_files import stage_file


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


def build_population_output_path(
    census_year: int, geography_level: GeographyLevel, state_code: str | None = None
) -> Path:
    """Build a relative Parquet path using the Census year, geography level, and state.

    For example, 1990 tracts with state code "10" produce
    ``1990/tracts/DE_1990_populations.parquet``. This only constructs the path; it does not create
    folders or write a table.

    Args:
        census_year (int): Census year used in the folder and filename.
        geography_level (GeographyLevel): Geographic units represented by the table.
        state_code (str | None): Two-digit state FIPS code, including its leading zero. Defaults
            to None for a national table, whose filename starts with "national".

    Returns:
        Path: Table path relative to the configured processed-population directory.

    Raises:
        ValueError: The supplied state code has no known postal abbreviation.
    """
    area_name = "national"

    if state_code is not None:
        state_abbreviations_by_fips = us.states.mapping("fips", "abbr")

        if state_code not in state_abbreviations_by_fips:
            raise ValueError(f"Unknown state FIPS code: {state_code}")

        area_name = state_abbreviations_by_fips[state_code]

    filename = f"{area_name}_{census_year}_populations.parquet"

    return Path(str(census_year)) / geography_level.value / filename


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
        white_population=int(population_df[PopulationColumn.WHITE].sum()),
        black_population=int(population_df[PopulationColumn.BLACK].sum()),
        poc_population=int(population_df[PopulationColumn.POC].sum()),
        comparison=comparison,
    )
