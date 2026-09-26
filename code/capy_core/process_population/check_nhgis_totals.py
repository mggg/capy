"""Compare historical population counts with state tables and Census reference workbooks."""

from pathlib import Path

import pandas as pd
import us

from capy_core.geography_types import GeographyLevel
from capy_core.population_table_columns import GeographyColumn, PopulationColumn
from capy_core.retrieve_data.state_codes import STATE_FIPS_CODES

from .nhgis_columns import NHGIS_COUNT_COLUMNS
from .save_tables import PopulationComparison


def check_historical_published_totals(
    states_df: pd.DataFrame, published_totals_workbook_path: Path, census_year: int
) -> None:
    """Check all 51 state totals and study groups against Census Working Paper 56's E table.

    Args:
        states_df (pd.DataFrame): Derived NHGIS state records for the 50 states and DC.
        published_totals_workbook_path (Path): Published E-3 (1980) or E-1 (1990) workbook in its
            original XLSX format.
        census_year (int): Census year, 1980 or 1990.

    Raises:
        OSError: The workbook cannot be read.
        ValueError: Headers, state coverage, or total/non-Hispanic White/Black counts disagree.
    """
    expected_state_codes = set(STATE_FIPS_CODES) - {"72"}

    if (
        set(states_df[GeographyColumn.STATE_CODE]) != expected_state_codes
        or states_df[GeographyColumn.STATE_CODE].duplicated().any()
    ):
        raise ValueError("Historical state reference must cover the 50 states and DC once each")

    published_totals_df = pd.read_excel(
        published_totals_workbook_path, header=None, dtype=str, keep_default_na=False
    )

    if published_totals_df.shape[0] < 5 or published_totals_df.shape[1] < 10:
        raise ValueError(
            f"Incomplete historical population reference: {published_totals_workbook_path}"
        )
    if f"{census_year} (100-Percent Data)" not in published_totals_df.iat[0, 0]:
        raise ValueError(
            "Historical reference has the wrong year or data series: "
            f"{published_totals_workbook_path}"
        )
    if published_totals_df.iat[3, 4] != "White" or published_totals_df.iat[3, 7] != "Black":
        raise ValueError(
            f"Historical reference race headings changed: {published_totals_workbook_path}"
        )
    if any(
        " ".join(published_totals_df.iat[4, column].split()) != "Not of Hispanic origin"
        for column in (6, 9)
    ):
        raise ValueError(
            "Historical reference Hispanic-origin headings changed: "
            f"{published_totals_workbook_path}"
        )

    state_codes_by_name = us.states.mapping("name", "fips")
    published_area_names = published_totals_df.iloc[:, 0].str.strip(" .")
    published_totals_df[GeographyColumn.STATE_CODE] = published_area_names.map(state_codes_by_name)
    published_state_totals_df = published_totals_df.loc[
        published_totals_df[GeographyColumn.STATE_CODE].isin(sorted(expected_state_codes))
    ].copy()

    if (
        len(published_state_totals_df) != 51
        or set(published_state_totals_df[GeographyColumn.STATE_CODE]) != expected_state_codes
    ):
        raise ValueError("Published historical reference must identify each state once")

    published_state_totals_df = published_state_totals_df.set_index(GeographyColumn.STATE_CODE)
    for population_column, workbook_column_index in (
        (PopulationColumn.TOTAL, 1),
        (PopulationColumn.WHITE, 6),
        (PopulationColumn.BLACK, 9),
    ):
        published_count_strings = pd.Series(published_state_totals_df[workbook_column_index])

        if not published_count_strings.str.fullmatch(r"[0-9]+").all():
            raise ValueError(f"Published {population_column} values must be nonnegative integers")

        published_state_counts = published_count_strings.map(int)
        nhgis_state_counts = pd.Series(
            states_df.set_index(GeographyColumn.STATE_CODE)[population_column]
        )

        if not nhgis_state_counts.eq(
            published_state_counts.reindex(nhgis_state_counts.index)
        ).all():
            raise ValueError(
                f"{census_year} {population_column} differs from published state totals"
            )


def check_nhgis_state_sum(
    population_df: pd.DataFrame,
    states_df: pd.DataFrame,
    census_year: int,
    geography_level: GeographyLevel,
) -> PopulationComparison:
    """Check each source count against the containing state and describe the comparison.

    Counties and 1990 smaller units partition states. The 1980 tract collection has incomplete
    coverage, so its sums may fall below state counts but must not exceed them. This bound cannot
    prove that every historically available tract is present.

    Args:
        population_df (pd.DataFrame): One state's checked records at the requested level.
        states_df (pd.DataFrame): Checked national state table for the same year.
        census_year (int): 1980 or 1990.
        geography_level (GeographyLevel): County, tract, block group, or block.

    Returns:
        PopulationComparison: Summary label for exact state sums or partial 1980 tract coverage.

    Raises:
        ValueError: The state is ambiguous/missing or a population sum fails its comparison.
    """
    state_codes = population_df[GeographyColumn.STATE_CODE].unique()
    if len(state_codes) != 1:
        raise ValueError("Expected a single state's NHGIS population records")

    state_reference_df = states_df.loc[states_df[GeographyColumn.STATE_CODE].eq(state_codes[0])]

    if len(state_reference_df) != 1:
        raise ValueError(f"Expected one reference for state {state_codes[0]}")

    partial_tract_coverage = census_year == 1980 and geography_level == GeographyLevel.TRACT
    for population_column in (
        *NHGIS_COUNT_COLUMNS[census_year],
        PopulationColumn.WHITE,
        PopulationColumn.BLACK,
        PopulationColumn.POC,
    ):
        observed_total = int(population_df[population_column].sum())
        reference_total = int(state_reference_df.iloc[0][population_column])

        if observed_total > reference_total or (
            not partial_tract_coverage and observed_total != reference_total
        ):
            raise ValueError(
                f"State {state_codes[0]}: {population_column} sums to {observed_total}, "
                f"reference {reference_total}"
            )

    if partial_tract_coverage:
        return PopulationComparison.PARTIAL_1980_TRACT_COVERAGE

    return PopulationComparison.NHGIS_COUNTS_MATCH_STATE
