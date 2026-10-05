"""Census API columns shared by download requests and population processing.

Race categories include Hispanic residents. The NON_HISPANIC_WHITE and NON_HISPANIC_BLACK
columns supply the study counts. HISPANIC includes residents of any race. The source variable
dictionaries are linked in
documentation/national_pipeline/01_raw_source_acquisition.md#census-population-variable-guide.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeAlias

from ..raw_file_requests import CensusDataset


class CensusGeographyColumn(StrEnum):
    """Census response fields for area names and geographic codes.

    Except NAME, these values also name geographic levels in API query parameters. Codes remain
    strings so leading zeros are preserved. STATE is shared with processed population tables.
    """

    NAME = "NAME"
    STATE = "state"
    COUNTY = "county"
    TRACT = "tract"
    BLOCK_GROUP = "block group"
    BLOCK = "block"
    PLACE = "place"


class Census2000PlColumn(StrEnum):
    """Population columns from the 2000 PL 94-171 Census API variable dictionary."""

    TOTAL = "PL001001"
    WHITE_ALONE = "PL001003"
    BLACK_ALONE = "PL001004"
    AMERICAN_INDIAN_ALASKA_NATIVE_ALONE = "PL001005"
    ASIAN_ALONE = "PL001006"
    NATIVE_HAWAIIAN_PACIFIC_ISLANDER_ALONE = "PL001007"
    OTHER_RACE_ALONE = "PL001008"
    TWO_OR_MORE_RACES = "PL001009"
    HISPANIC = "PL002002"
    NON_HISPANIC_WHITE = "PL002005"
    NON_HISPANIC_BLACK = "PL002006"


class Census2000Sf1Column(StrEnum):
    """Population columns from the 2000 SF1 Census API variable dictionary."""

    TOTAL = "P001001"
    WHITE_ALONE = "P003003"
    BLACK_ALONE = "P003004"
    AMERICAN_INDIAN_ALASKA_NATIVE_ALONE = "P003005"
    ASIAN_ALONE = "P003006"
    NATIVE_HAWAIIAN_PACIFIC_ISLANDER_ALONE = "P003007"
    OTHER_RACE_ALONE = "P003008"
    TWO_OR_MORE_RACES = "P003009"
    HISPANIC = "P004002"
    NON_HISPANIC_WHITE = "P004005"
    NON_HISPANIC_BLACK = "P004006"


class Census2010PlColumn(StrEnum):
    """Population columns from the 2010 PL 94-171 Census API variable dictionary."""

    TOTAL = "P001001"
    WHITE_ALONE = "P001003"
    BLACK_ALONE = "P001004"
    AMERICAN_INDIAN_ALASKA_NATIVE_ALONE = "P001005"
    ASIAN_ALONE = "P001006"
    NATIVE_HAWAIIAN_PACIFIC_ISLANDER_ALONE = "P001007"
    OTHER_RACE_ALONE = "P001008"
    TWO_OR_MORE_RACES = "P001009"
    HISPANIC = "P002002"
    NON_HISPANIC_WHITE = "P002005"
    NON_HISPANIC_BLACK = "P002006"


class Census2020PlColumn(StrEnum):
    """Population columns from the 2020 PL 94-171 Census API variable dictionary."""

    TOTAL = "P1_001N"
    WHITE_ALONE = "P1_003N"
    BLACK_ALONE = "P1_004N"
    AMERICAN_INDIAN_ALASKA_NATIVE_ALONE = "P1_005N"
    ASIAN_ALONE = "P1_006N"
    NATIVE_HAWAIIAN_PACIFIC_ISLANDER_ALONE = "P1_007N"
    OTHER_RACE_ALONE = "P1_008N"
    TWO_OR_MORE_RACES = "P1_009N"
    HISPANIC = "P2_002N"
    NON_HISPANIC_WHITE = "P2_005N"
    NON_HISPANIC_BLACK = "P2_006N"


CensusPopulationColumn: TypeAlias = (
    Census2000PlColumn | Census2000Sf1Column | Census2010PlColumn | Census2020PlColumn
)


@dataclass(frozen=True)
class CensusPopulationColumns:
    """Source columns used to derive study counts and check race and Hispanic-origin totals.

    White-alone and Black-alone counts include Hispanic residents. The non_hispanic fields
    select the study populations. Named roles do not depend on downloaded column order.
    """

    total: CensusPopulationColumn
    white_alone: CensusPopulationColumn
    black_alone: CensusPopulationColumn
    other_race_categories: tuple[CensusPopulationColumn, ...]
    hispanic: CensusPopulationColumn
    non_hispanic_white: CensusPopulationColumn
    non_hispanic_black: CensusPopulationColumn

    @property
    def race_categories(self) -> tuple[CensusPopulationColumn, ...]:
        """The seven mutually exclusive race categories, including Hispanic residents."""
        return (self.white_alone, self.black_alone, *self.other_race_categories)

    @property
    def count_columns(self) -> tuple[CensusPopulationColumn, ...]:
        """All eleven source count columns in the same conceptual order across datasets."""
        return (
            self.total,
            *self.race_categories,
            self.hispanic,
            self.non_hispanic_white,
            self.non_hispanic_black,
        )


CENSUS_POPULATION_COLUMNS: dict[
    tuple[Literal[2000, 2010, 2020], CensusDataset], CensusPopulationColumns
] = {
    (2000, CensusDataset.PL_94_171): CensusPopulationColumns(
        total=Census2000PlColumn.TOTAL,
        white_alone=Census2000PlColumn.WHITE_ALONE,
        black_alone=Census2000PlColumn.BLACK_ALONE,
        other_race_categories=(
            Census2000PlColumn.AMERICAN_INDIAN_ALASKA_NATIVE_ALONE,
            Census2000PlColumn.ASIAN_ALONE,
            Census2000PlColumn.NATIVE_HAWAIIAN_PACIFIC_ISLANDER_ALONE,
            Census2000PlColumn.OTHER_RACE_ALONE,
            Census2000PlColumn.TWO_OR_MORE_RACES,
        ),
        hispanic=Census2000PlColumn.HISPANIC,
        non_hispanic_white=Census2000PlColumn.NON_HISPANIC_WHITE,
        non_hispanic_black=Census2000PlColumn.NON_HISPANIC_BLACK,
    ),
    (2000, CensusDataset.SUMMARY_FILE_1): CensusPopulationColumns(
        total=Census2000Sf1Column.TOTAL,
        white_alone=Census2000Sf1Column.WHITE_ALONE,
        black_alone=Census2000Sf1Column.BLACK_ALONE,
        other_race_categories=(
            Census2000Sf1Column.AMERICAN_INDIAN_ALASKA_NATIVE_ALONE,
            Census2000Sf1Column.ASIAN_ALONE,
            Census2000Sf1Column.NATIVE_HAWAIIAN_PACIFIC_ISLANDER_ALONE,
            Census2000Sf1Column.OTHER_RACE_ALONE,
            Census2000Sf1Column.TWO_OR_MORE_RACES,
        ),
        hispanic=Census2000Sf1Column.HISPANIC,
        non_hispanic_white=Census2000Sf1Column.NON_HISPANIC_WHITE,
        non_hispanic_black=Census2000Sf1Column.NON_HISPANIC_BLACK,
    ),
    (2010, CensusDataset.PL_94_171): CensusPopulationColumns(
        total=Census2010PlColumn.TOTAL,
        white_alone=Census2010PlColumn.WHITE_ALONE,
        black_alone=Census2010PlColumn.BLACK_ALONE,
        other_race_categories=(
            Census2010PlColumn.AMERICAN_INDIAN_ALASKA_NATIVE_ALONE,
            Census2010PlColumn.ASIAN_ALONE,
            Census2010PlColumn.NATIVE_HAWAIIAN_PACIFIC_ISLANDER_ALONE,
            Census2010PlColumn.OTHER_RACE_ALONE,
            Census2010PlColumn.TWO_OR_MORE_RACES,
        ),
        hispanic=Census2010PlColumn.HISPANIC,
        non_hispanic_white=Census2010PlColumn.NON_HISPANIC_WHITE,
        non_hispanic_black=Census2010PlColumn.NON_HISPANIC_BLACK,
    ),
    (2020, CensusDataset.PL_94_171): CensusPopulationColumns(
        total=Census2020PlColumn.TOTAL,
        white_alone=Census2020PlColumn.WHITE_ALONE,
        black_alone=Census2020PlColumn.BLACK_ALONE,
        other_race_categories=(
            Census2020PlColumn.AMERICAN_INDIAN_ALASKA_NATIVE_ALONE,
            Census2020PlColumn.ASIAN_ALONE,
            Census2020PlColumn.NATIVE_HAWAIIAN_PACIFIC_ISLANDER_ALONE,
            Census2020PlColumn.OTHER_RACE_ALONE,
            Census2020PlColumn.TWO_OR_MORE_RACES,
        ),
        hispanic=Census2020PlColumn.HISPANIC,
        non_hispanic_white=Census2020PlColumn.NON_HISPANIC_WHITE,
        non_hispanic_black=Census2020PlColumn.NON_HISPANIC_BLACK,
    ),
}
