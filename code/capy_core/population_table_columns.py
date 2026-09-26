"""Column labels for counts, geography, and sources in processed population tables."""

from enum import StrEnum


class PopulationColumn(StrEnum):
    """Study population counts, with enum values matching the column labels written to disk.

    NON_HISPANIC_WHITE and NON_HISPANIC_BLACK count non-Hispanic residents in the respective
    race groups. Their saved column labels are WHITE and BLACK. POC counts everyone except
    non-Hispanic White residents, so it includes more than the non-Hispanic Black group.
    """

    TOTAL = "TOTPOP"
    NON_HISPANIC_WHITE = "WHITE"
    NON_HISPANIC_BLACK = "BLACK"
    POC = "POC"


class GeographyColumn(StrEnum):
    """Geographic identifiers and resolution of each processed population record.

    Geographic IDs and state codes remain strings to preserve leading zeros. COUNTY_CODE is the
    three-digit county component within a state. GEOGRAPHY_LEVEL identifies the kind of unit,
    such as a tract or block. Enum values are saved column labels.
    """

    GEOGRAPHIC_ID = "GEOID"
    STATE_CODE = "state"
    COUNTY_CODE = "county"
    GEOGRAPHY_LEVEL = "GEOGRAPHY_LEVEL"


class PopulationSourceColumn(StrEnum):
    """Census year, dataset, and original record location for each processed population row.

    SOURCE_FILE gives the file path relative to the raw-data directory. SOURCE_MEMBER names
    the CSV inside an NHGIS archive, and SOURCE_ROW counts data rows from one, excluding headers.
    Enum values are the column labels written to disk.
    """

    CENSUS_YEAR = "CENSUS_YEAR"
    CENSUS_DATASET = "CENSUS_DATASET"
    SOURCE_FILE = "SOURCE_FILE"
    SOURCE_MEMBER = "SOURCE_MEMBER"
    SOURCE_ROW = "SOURCE_ROW"
