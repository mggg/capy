"""Compare modern population tables with state aggregates and published resident totals."""

from pathlib import Path

import pandas as pd

from national_pipeline.geography_types import GeographyLevel
from national_pipeline.population_table_columns import GeographyColumn, PopulationColumn
from national_pipeline.retrieve_data.census.table_columns import (
    CENSUS_POPULATION_COLUMNS,
    CensusGeographyColumn,
)
from national_pipeline.retrieve_data.raw_file_requests import CensusDataset, CensusFileRequest
from national_pipeline.retrieve_data.state_codes import STATE_FIPS_CODES

from .save_tables import PopulationComparison


def check_published_state_totals(
    states_df: pd.DataFrame, published_totals_csv_path: Path, census_year: int
) -> None:
    """Compare each state's total with the Census 2020 release's historical resident counts.

    Args:
        states_df (pd.DataFrame): Checked Census state table with NAME, state, and TOTPOP columns.
        published_totals_csv_path (Path): Unmodified apportionment CSV with historical resident
            counts.
        census_year (int): Year to select in that reference, including 2000 or 2010.

    Raises:
        OSError: The reference cannot be read.
        ValueError: A state is missing/repeated or its resident total differs from the reference.
    """
    if set(states_df[GeographyColumn.STATE_CODE]) != set(STATE_FIPS_CODES):
        raise ValueError("State reference must cover the 50 states, DC, and Puerto Rico")

    published_totals_df = pd.read_csv(published_totals_csv_path, dtype=str, keep_default_na=False)
    required_columns = {"Name", "Geography Type", "Year", "Resident Population"}

    if not required_columns.issubset(published_totals_df.columns):
        raise ValueError(f"Missing resident population columns in {published_totals_csv_path}")

    published_state_totals_df = published_totals_df.loc[
        published_totals_df["Year"].eq(str(census_year))
        & published_totals_df["Name"].isin(states_df[CensusGeographyColumn.NAME])
    ]

    if published_state_totals_df["Name"].duplicated().any() or set(
        published_state_totals_df["Name"]
    ) != set(states_df[CensusGeographyColumn.NAME]):
        raise ValueError(f"Published reference must identify each state once for {census_year}")

    resident_count_strings = published_state_totals_df["Resident Population"].str.replace(
        ",", "", regex=False
    )

    if not resident_count_strings.str.fullmatch(r"[0-9]+").all():
        raise ValueError("Published resident populations must be nonnegative integers")

    published_totals_by_state_name = dict(
        zip(published_state_totals_df["Name"], map(int, resident_count_strings), strict=True)
    )

    for state_name, state_total in zip(
        states_df[CensusGeographyColumn.NAME], states_df[PopulationColumn.TOTAL], strict=True
    ):
        if state_total != published_totals_by_state_name[state_name]:
            raise ValueError(f"{census_year} resident population differs for {state_name}")


def check_population_state_sum(
    population_df: pd.DataFrame, request: CensusFileRequest, states_df: pd.DataFrame
) -> PopulationComparison:
    """Compare every requested count with the containing state's corresponding count.

    Counties, tracts, block groups, and blocks each partition a state. Places do not cover all
    residents, so they are deliberately excluded from this comparison. SF1 and PL column names
    are matched by population definition rather than their position in the downloaded response.

    Args:
        population_df (pd.DataFrame): Checked, complete statewide table for one geography level.
        request (CensusFileRequest): Year, dataset, level, and state represented by that table.
        states_df (pd.DataFrame): Checked PL state reference for the same year.

    Returns:
        PopulationComparison: Counts matched the state, or places do not partition the state.

    Raises:
        ValueError: A national state table was passed, the containing state is missing, or
            any of the eleven population sums differs.
    """
    if request.geography_level == GeographyLevel.STATE:
        raise ValueError("Compare national state tables with published totals instead")

    if request.geography_level == GeographyLevel.PLACE:
        return PopulationComparison.PLACES_DO_NOT_PARTITION_STATE

    state_reference_df = states_df.loc[states_df[GeographyColumn.STATE_CODE].eq(request.state_code)]

    if len(state_reference_df) != 1:
        raise ValueError(f"Expected one reference row for state {request.state_code}")

    local_columns = CENSUS_POPULATION_COLUMNS[request.census_year, request.dataset]
    state_columns = CENSUS_POPULATION_COLUMNS[request.census_year, CensusDataset.PL_94_171]

    for local_column, state_column in zip(
        local_columns.count_columns, state_columns.count_columns, strict=True
    ):
        observed_total = int(population_df[local_column].sum())
        reference_total = int(state_reference_df.iloc[0][state_column])

        if observed_total != reference_total:
            raise ValueError(
                f"State {request.state_code}: {local_column} sums to {observed_total}, "
                f"expected {reference_total}"
            )

    return PopulationComparison.CENSUS_COUNTS_MATCH_STATE
