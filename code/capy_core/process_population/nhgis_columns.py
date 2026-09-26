"""NHGIS geographic fields, population codes, and demographic groups used in processing."""

from enum import StrEnum


class NhgisGeographyColumn(StrEnum):
    """Source fields identifying NHGIS records in both 1980 and 1990 population tables.

    GISJOIN is preserved as the processed GEOID. STATEA and COUNTYA contain the state and
    county codes; they remain strings so leading zeros are retained.
    """

    GEOGRAPHIC_ID = "GISJOIN"
    STATE_CODE = "STATEA"
    COUNTY_CODE = "COUNTYA"
    CENSUS_YEAR = "YEAR"


class Nhgis1980Column(StrEnum):
    """Whole-area counts from the 1980_STF1 NT1A, NT7, NT9A, and NT9B tables.

    Names follow the codebook included in the downloaded NHGIS archive. Race counts include
    Hispanic residents; HISPANIC_* members identify the subsets used to check and subtract them.
    """

    TOTAL = "C7L001"
    WHITE = "C9D001"
    BLACK = "C9D002"
    AMERICAN_INDIAN = "C9D003"
    ESKIMO = "C9D004"
    ALEUT = "C9D005"
    JAPANESE = "C9D006"
    CHINESE = "C9D007"
    FILIPINO = "C9D008"
    KOREAN = "C9D009"
    ASIAN_INDIAN = "C9D010"
    VIETNAMESE = "C9D011"
    HAWAIIAN = "C9D012"
    GUAMANIAN = "C9D013"
    SAMOAN = "C9D014"
    OTHER_RACE = "C9D015"
    HISPANIC_TOTAL = "C9F001"
    HISPANIC_WHITE = "C9G001"
    HISPANIC_BLACK = "C9G002"
    HISPANIC_INDIGENOUS_ASIAN_PACIFIC_ISLANDER = "C9G003"
    HISPANIC_OTHER_RACE = "C9G004"


class Nhgis1990Column(StrEnum):
    """Whole-area counts from 1990_STF1 tables NP1 and NP10 in the NHGIS archive codebook.

    NP10 separates Hispanic and non-Hispanic residents within each race group. The two
    non-Hispanic White and Black counts can therefore be used directly as study populations.
    """

    TOTAL = "ET1001"
    NON_HISPANIC_WHITE = "ET2001"
    NON_HISPANIC_BLACK = "ET2002"
    NON_HISPANIC_AMERICAN_INDIAN_ESKIMO_ALEUT = "ET2003"
    NON_HISPANIC_ASIAN_PACIFIC_ISLANDER = "ET2004"
    NON_HISPANIC_OTHER_RACE = "ET2005"
    HISPANIC_WHITE = "ET2006"
    HISPANIC_BLACK = "ET2007"
    HISPANIC_AMERICAN_INDIAN_ESKIMO_ALEUT = "ET2008"
    HISPANIC_ASIAN_PACIFIC_ISLANDER = "ET2009"
    HISPANIC_OTHER_RACE = "ET2010"


# NT9B combines these NT7 groups in a single Hispanic-origin count.
NHGIS_1980_INDIGENOUS_ASIAN_PACIFIC_ISLANDER_COLUMNS = (
    Nhgis1980Column.AMERICAN_INDIAN,
    Nhgis1980Column.ESKIMO,
    Nhgis1980Column.ALEUT,
    Nhgis1980Column.JAPANESE,
    Nhgis1980Column.CHINESE,
    Nhgis1980Column.FILIPINO,
    Nhgis1980Column.KOREAN,
    Nhgis1980Column.ASIAN_INDIAN,
    Nhgis1980Column.VIETNAMESE,
    Nhgis1980Column.HAWAIIAN,
    Nhgis1980Column.GUAMANIAN,
    Nhgis1980Column.SAMOAN,
)
NHGIS_1980_RACE_COLUMNS = (
    Nhgis1980Column.WHITE,
    Nhgis1980Column.BLACK,
    *NHGIS_1980_INDIGENOUS_ASIAN_PACIFIC_ISLANDER_COLUMNS,
    Nhgis1980Column.OTHER_RACE,
)
NHGIS_1980_HISPANIC_RACE_COLUMNS = (
    Nhgis1980Column.HISPANIC_WHITE,
    Nhgis1980Column.HISPANIC_BLACK,
    Nhgis1980Column.HISPANIC_INDIGENOUS_ASIAN_PACIFIC_ISLANDER,
    Nhgis1980Column.HISPANIC_OTHER_RACE,
)
NHGIS_1990_RACE_ORIGIN_COLUMNS = tuple(
    column for column in Nhgis1990Column if column != Nhgis1990Column.TOTAL
)
NHGIS_COUNT_COLUMNS = {
    1980: tuple(Nhgis1980Column),
    1990: tuple(Nhgis1990Column),
}
