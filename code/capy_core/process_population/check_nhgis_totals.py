"""Compare historical population counts with state tables and Census reference workbooks."""

from pathlib import Path

import pandas as pd
import us

from capy_core.geography_types import GeographyLevel
from capy_core.population_table_columns import GeographyColumn, PopulationColumn
from capy_core.retrieve_data.census.build_published_file_requests import (
    HISTORICAL_STUDY_TOTALS_FILENAMES,
    RACE_TOTALS_1980_FILENAME,
)
from capy_core.retrieve_data.nhgis.table_columns import (
    NHGIS_COUNT_COLUMNS,
    Nhgis1980Column,
    Nhgis1990Column,
)
from capy_core.retrieve_data.state_codes import STATE_FIPS_CODES

from .save_tables import PopulationComparison


def check_historical_published_totals(
    states_df: pd.DataFrame, reference_directory: Path, census_year: int
) -> None:
    """Compare all 51 NHGIS state populations with Census Working Paper 56 workbooks.

    E-3 (1980) and E-1 (1990) check the study's total, non-Hispanic White, and non-Hispanic
    Black counts. A-3 supplies the separate 1980 race groups that E-3 combines; E-1 supplies
    all ten 1990 race-by-Hispanic-origin groups. Inputs are not changed.

    Args:
        states_df (pd.DataFrame): Derived NHGIS records for the 50 states and DC, including
            original count columns.
        reference_directory (Path): Configured folder containing the published XLSX workbooks.
        census_year (int): Census year, 1980 or 1990.

    Raises:
        OSError: A required workbook cannot be read.
        ValueError: The year, workbook layout, state coverage, or population comparisons fail.
    """
    if census_year not in HISTORICAL_STUDY_TOTALS_FILENAMES:
        raise ValueError("Published historical comparisons support 1980 and 1990")

    expected_state_codes = set(STATE_FIPS_CODES) - {"72"}

    if (
        set(states_df[GeographyColumn.STATE_CODE]) != expected_state_codes
        or states_df[GeographyColumn.STATE_CODE].duplicated().any()
    ):
        raise ValueError("Historical state reference must cover the 50 states and DC once each")

    states_df = states_df.set_index(GeographyColumn.STATE_CODE)
    workbook_path = reference_directory / HISTORICAL_STUDY_TOTALS_FILENAMES[census_year]
    race_headings = {4: "White", 7: "Black"}

    if census_year == 1990:
        race_headings.update(
            {
                10: "American Indian, Eskimo, and Aleut",
                13: "Asian and Pacific Islander",
                16: "Other race",
            }
        )

    expected_headings = {(3, column): heading for column, heading in race_headings.items()}

    for column in race_headings:
        expected_headings[4, column + 1] = "Hispanic origin"
        expected_headings[4, column + 2] = "Not of Hispanic origin"

    published_states_df = read_published_state_reference(
        workbook_path, census_year, expected_headings
    )

    comparison_columns: dict[PopulationColumn | Nhgis1990Column, int] = {
        PopulationColumn.TOTAL: 1,
        PopulationColumn.WHITE: 6,
        PopulationColumn.BLACK: 9,
    }

    if census_year == 1990:
        comparison_columns.update(
            {
                Nhgis1990Column.NON_HISPANIC_WHITE: 6,
                Nhgis1990Column.NON_HISPANIC_BLACK: 9,
                Nhgis1990Column.NON_HISPANIC_AMERICAN_INDIAN_ESKIMO_ALEUT: 12,
                Nhgis1990Column.NON_HISPANIC_ASIAN_PACIFIC_ISLANDER: 15,
                Nhgis1990Column.NON_HISPANIC_OTHER_RACE: 18,
                Nhgis1990Column.HISPANIC_WHITE: 5,
                Nhgis1990Column.HISPANIC_BLACK: 8,
                Nhgis1990Column.HISPANIC_AMERICAN_INDIAN_ESKIMO_ALEUT: 11,
                Nhgis1990Column.HISPANIC_ASIAN_PACIFIC_ISLANDER: 14,
                Nhgis1990Column.HISPANIC_OTHER_RACE: 17,
            }
        )

    for population_column, workbook_column in comparison_columns.items():
        compare_published_state_counts(
            pd.Series(states_df[population_column]),
            pd.Series(published_states_df[workbook_column]),
            f"{workbook_path.name}: {population_column}",
        )

    if census_year == 1980:
        check_1980_published_race_totals(states_df, reference_directory / RACE_TOTALS_1980_FILENAME)


def check_1980_published_race_totals(states_df: pd.DataFrame, workbook_path: Path) -> None:
    """Compare 1980 NHGIS race and Hispanic totals with A-3, without changing either table.

    Args:
        states_df (pd.DataFrame): Validated 1980 state records indexed by two-digit state code.
        workbook_path (Path): Original A-3 workbook, which distinguishes race groups combined in E-3.

    Raises:
        OSError: The workbook cannot be read.
        ValueError: Its layout, state coverage, or population counts disagree.
    """
    race_headings = {
        3: "White",
        5: "Black",
        7: "American Indian, Eskimo, and Aleut",
        9: "Asian and Pacific Islander",
        11: "Other race",
    }
    expected_headings = {(4, column): heading for column, heading in race_headings.items()}
    expected_headings[2, 13] = "Spanish origin (of any race)"

    for column in (*race_headings, 13):
        expected_headings[5, column] = "Number"

    published_states_df = read_published_state_reference(workbook_path, 1980, expected_headings)
    source_columns_by_workbook_column = {
        3: (Nhgis1980Column.WHITE,),
        5: (Nhgis1980Column.BLACK,),
        7: (Nhgis1980Column.AMERICAN_INDIAN, Nhgis1980Column.ESKIMO, Nhgis1980Column.ALEUT),
        9: (
            Nhgis1980Column.JAPANESE,
            Nhgis1980Column.CHINESE,
            Nhgis1980Column.FILIPINO,
            Nhgis1980Column.KOREAN,
            Nhgis1980Column.ASIAN_INDIAN,
            Nhgis1980Column.VIETNAMESE,
            Nhgis1980Column.HAWAIIAN,
            Nhgis1980Column.GUAMANIAN,
            Nhgis1980Column.SAMOAN,
        ),
        11: (Nhgis1980Column.OTHER_RACE,),
        13: (Nhgis1980Column.HISPANIC_TOTAL,),
    }

    for workbook_column, source_columns in source_columns_by_workbook_column.items():
        nhgis_counts = states_df[list(source_columns)].sum(axis=1)
        population_label = race_headings.get(workbook_column, "Hispanic origin")

        compare_published_state_counts(
            nhgis_counts,
            pd.Series(published_states_df[workbook_column]),
            f"{workbook_path.name}: {population_label}",
        )


def read_published_state_reference(
    workbook_path: Path, census_year: int, expected_headings: dict[tuple[int, int], str]
) -> pd.DataFrame:
    """Read a Working Paper 56 workbook and retain exactly one row per state and DC.

    Args:
        workbook_path (Path): Published XLSX file, read without modifying it.
        census_year (int): Expected year of the 100-percent Census counts.
        expected_headings (dict[tuple[int, int], str]): Required text at zero-based row/column
            positions. Line breaks and repeated spaces in the workbook are ignored.

    Returns:
        pd.DataFrame: String-valued workbook columns indexed by two-digit state code.

    Raises:
        OSError: The workbook cannot be read.
        ValueError: Its year, headings, or state coverage differ from the expected layout.
    """
    published_df = pd.read_excel(workbook_path, header=None, dtype=str, keep_default_na=False)

    if published_df.empty or f"{census_year} (100-Percent Data)" not in published_df.iat[0, 0]:
        raise ValueError(f"Historical reference has the wrong year or data series: {workbook_path}")

    for (row, column), heading in expected_headings.items():
        if (
            row >= len(published_df)
            or column >= len(published_df.columns)
            or " ".join(published_df.iat[row, column].split()) != heading
        ):
            raise ValueError(f"Expected heading {heading!r} at ({row}, {column}): {workbook_path}")

    expected_state_codes = set(STATE_FIPS_CODES) - {"72"}
    state_codes_by_name = us.states.mapping("name", "fips")
    published_area_names = published_df.iloc[:, 0].str.strip(" .")
    published_df[GeographyColumn.STATE_CODE] = published_area_names.map(state_codes_by_name)
    published_states_df = published_df.loc[
        published_df[GeographyColumn.STATE_CODE].isin(sorted(expected_state_codes))
    ].copy()

    if (
        len(published_states_df) != 51
        or set(published_states_df[GeographyColumn.STATE_CODE]) != expected_state_codes
    ):
        raise ValueError(f"Published reference must identify each state once: {workbook_path}")

    return published_states_df.set_index(GeographyColumn.STATE_CODE)


def compare_published_state_counts(
    nhgis_counts: pd.Series, published_count_strings: pd.Series, comparison_label: str
) -> None:
    """Require exact agreement for a population group, aligning the tables by state code.

    Args:
        nhgis_counts (pd.Series): Integer counts indexed by state code.
        published_count_strings (pd.Series): Workbook counts indexed by state code.
        comparison_label (str): Workbook and population label to identify a failed comparison.

    Raises:
        ValueError: A published count is invalid or a state's population disagrees.
    """
    if not published_count_strings.str.fullmatch(r"[0-9]+", na=False).all():
        raise ValueError(f"Published counts must be nonnegative integers: {comparison_label}")

    published_counts = published_count_strings.map(int).reindex(nhgis_counts.index)
    differing_states = [
        state_code
        for state_code, matches in nhgis_counts.eq(published_counts).items()
        if not matches
    ]

    if differing_states:
        raise ValueError(
            f"{comparison_label} differs from published totals in states {differing_states}"
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
