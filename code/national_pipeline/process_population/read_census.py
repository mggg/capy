"""Read modern Census tables, preserve source records, and derive the study's populations."""

from pathlib import Path

import pandas as pd

from national_pipeline.geography_types import GeographyLevel
from national_pipeline.population_table_columns import (
    GeographyColumn,
    PopulationColumn,
    PopulationSourceColumn,
)
from national_pipeline.retrieve_data.census.read_tables import load_census_table
from national_pipeline.retrieve_data.census.table_columns import (
    CENSUS_POPULATION_COLUMNS,
    CensusGeographyColumn,
    CensusPopulationColumns,
)
from national_pipeline.retrieve_data.raw_file_requests import CensusFileRequest

GEOGRAPHIC_COLUMNS = {
    GeographyLevel.STATE: {CensusGeographyColumn.STATE: 2},
    GeographyLevel.COUNTY: {CensusGeographyColumn.STATE: 2, CensusGeographyColumn.COUNTY: 3},
    GeographyLevel.TRACT: {
        CensusGeographyColumn.STATE: 2,
        CensusGeographyColumn.COUNTY: 3,
        CensusGeographyColumn.TRACT: 6,
    },
    GeographyLevel.BLOCK_GROUP: {
        CensusGeographyColumn.STATE: 2,
        CensusGeographyColumn.COUNTY: 3,
        CensusGeographyColumn.TRACT: 6,
        CensusGeographyColumn.BLOCK_GROUP: 1,
    },
    GeographyLevel.BLOCK: {
        CensusGeographyColumn.STATE: 2,
        CensusGeographyColumn.COUNTY: 3,
        CensusGeographyColumn.TRACT: 6,
        CensusGeographyColumn.BLOCK: 4,
    },
    GeographyLevel.PLACE: {CensusGeographyColumn.STATE: 2, CensusGeographyColumn.PLACE: 5},
}


def read_census_population(population_json_path: Path, request: CensusFileRequest) -> pd.DataFrame:
    """Read one raw table, check its records, and add geographic IDs and study counts.

    No rows are dropped or combined, including rows with zero population. Source geographic
    columns stay unchanged; only GEOID uses normalized tract codes. SOURCE_ROW counts data rows
    from one, excluding the JSON header. The returned table is sorted by GEOID.

    Args:
        population_json_path (Path): Downloaded Census API JSON file.
        request (CensusFileRequest): Year, dataset, geography, and expected state for this file.

    Returns:
        pd.DataFrame: Original columns, integer population counts, and derived/lineage columns.

    Raises:
        OSError: Reading the file fails.
        ValueError: Columns, identifiers, or population counts fail their checks.
    """
    header, *rows = load_census_table(population_json_path)
    population_columns = CENSUS_POPULATION_COLUMNS.get((request.census_year, request.dataset))

    if population_columns is None:
        raise ValueError("Unsupported Census year and dataset for population processing")

    if not all(isinstance(column, str) for column in header):
        raise ValueError(f"Census column names must be strings in {population_json_path}")

    expected_columns = {
        CensusGeographyColumn.NAME,
        *population_columns.count_columns,
        *GEOGRAPHIC_COLUMNS[request.geography_level],
    }

    if len(header) != len(set(header)) or set(header) != expected_columns:
        raise ValueError(
            f"Unexpected Census columns in {population_json_path}; "
            f"expected {sorted(str(column) for column in expected_columns)}"
        )

    population_df = pd.DataFrame(rows, columns=pd.Index(header))
    population_df[PopulationSourceColumn.SOURCE_ROW] = range(1, len(population_df) + 1)
    population_df[GeographyColumn.GEOGRAPHIC_ID] = build_census_geographic_ids(
        population_df, request
    )

    counts_df = convert_and_check_census_population_counts(population_df, population_columns)
    population_df[counts_df.columns] = counts_df

    population_df[PopulationColumn.TOTAL] = population_df[population_columns.total]
    population_df[PopulationColumn.NON_HISPANIC_WHITE] = population_df[
        population_columns.non_hispanic_white
    ]
    population_df[PopulationColumn.NON_HISPANIC_BLACK] = population_df[
        population_columns.non_hispanic_black
    ]
    population_df[PopulationColumn.POC] = (
        population_df[PopulationColumn.TOTAL] - population_df[PopulationColumn.NON_HISPANIC_WHITE]
    )

    population_df[PopulationSourceColumn.SOURCE_FILE] = request.destination_relative_path
    population_df[PopulationSourceColumn.CENSUS_YEAR] = request.census_year
    population_df[PopulationSourceColumn.CENSUS_DATASET] = request.dataset.value
    population_df[GeographyColumn.GEOGRAPHY_LEVEL] = request.geography_level.value

    return population_df.sort_values(GeographyColumn.GEOGRAPHIC_ID).reset_index(drop=True)


def build_census_geographic_ids(
    population_df: pd.DataFrame, request: CensusFileRequest
) -> pd.Series:
    """Join checked string components into unique Census GEOIDs without changing source columns.

    Args:
        population_df (pd.DataFrame): Source records with state, county, and other required ID
            columns.
        request (CensusFileRequest): Geography level, Census year, and expected state.

    Returns:
        pd.Series: Unique geographic identifiers with leading zeros preserved.

    Raises:
        ValueError: An ID is missing, malformed, duplicated, or belongs to another state.
    """
    geographic_ids = pd.Series("", index=population_df.index, dtype="string")

    for geographic_column, code_width in GEOGRAPHIC_COLUMNS[request.geography_level].items():
        geographic_codes = pd.Series(population_df[geographic_column], index=population_df.index)

        if not all(isinstance(geographic_code, str) for geographic_code in geographic_codes):
            raise ValueError(f"Census {geographic_column} identifiers must be strings")

        if geographic_column == CensusGeographyColumn.TRACT and request.census_year == 2000:
            # The 2000 API omits trailing decimal digits: 0401 becomes 040100, not 000401.
            # Keep the downloaded tract column alongside the normalized GEOID for traceability.
            short_tract_codes = geographic_codes.str.fullmatch(r"[0-9]{4}")
            geographic_codes = geographic_codes.copy()
            geographic_codes.loc[short_tract_codes] = geographic_codes.loc[short_tract_codes] + "00"

        if not geographic_codes.str.fullmatch(r"[0-9]{" + str(code_width) + "}").all():
            raise ValueError(
                f"Census {geographic_column} identifiers must have {code_width} digits"
            )

        geographic_ids += geographic_codes

    if request.state_code is not None and any(
        state_code != request.state_code for state_code in population_df[GeographyColumn.STATE_CODE]
    ):
        raise ValueError(f"Population table contains a state other than {request.state_code}")

    if geographic_ids.duplicated().any():
        raise ValueError("Duplicate Census GEOIDs after normalization")

    return geographic_ids


def convert_and_check_census_population_counts(
    population_df: pd.DataFrame, population_columns: CensusPopulationColumns
) -> pd.DataFrame:
    """Return integer count columns after checking their demographic relationships.

    Args:
        population_df (pd.DataFrame): Source records, left unchanged on success and failure.
        population_columns (CensusPopulationColumns): Total, race, and Hispanic-origin column
            definitions.

    Returns:
        pd.DataFrame: Only the eleven count columns, containing exact Python integers and
            retaining the input row index. The caller assigns them to its working table.

    Raises:
        ValueError: Counts are missing, negative, noninteger, or inconsistent with each other.
    """
    counts_df = pd.DataFrame(index=population_df.index)

    for population_column in population_columns.count_columns:
        count_strings = population_df[population_column].astype("string")

        if not count_strings.str.fullmatch(r"[0-9]+").fillna(False).all():
            raise ValueError(
                f"{population_column} must contain nonnegative integer counts in every row"
            )

        # Python integers keep population sums exact instead of wrapping at the int64 limit.
        counts_df[population_column] = pd.Series(
            [int(count_string) for count_string in count_strings],
            index=population_df.index,
            dtype=object,
        )

    total_population = counts_df[population_columns.total]
    non_hispanic_white = counts_df[population_columns.non_hispanic_white]
    non_hispanic_black = counts_df[population_columns.non_hispanic_black]
    hispanic_population = counts_df[population_columns.hispanic]
    race_category_total = counts_df[list(population_columns.race_categories)].sum(axis=1)

    if not race_category_total.eq(total_population).all():
        raise ValueError("Race category counts do not sum to total population")

    if (hispanic_population > total_population).any():
        raise ValueError("Hispanic population exceeds total population")

    if (non_hispanic_white > counts_df[population_columns.white_alone]).any():
        raise ValueError("Non-Hispanic White population exceeds White-alone population")

    if (non_hispanic_black > counts_df[population_columns.black_alone]).any():
        raise ValueError("Non-Hispanic Black population exceeds Black-alone population")

    if (non_hispanic_white + non_hispanic_black > total_population - hispanic_population).any():
        raise ValueError("White and Black study counts exceed non-Hispanic population")

    return counts_df
