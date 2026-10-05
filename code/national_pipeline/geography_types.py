"""Shared names for geographic units and the areas used to organize the analysis."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class GeographyLevel(StrEnum):
    """Kinds of geographic units, with string values used in configuration and folder names.

    Counties, tracts, block groups, and blocks can become graph nodes. Places help define city
    study areas; states provide reference population totals. Provider-specific codes are kept in
    the Census and NHGIS request code.
    """

    STATE = "states"
    COUNTY = "counties"
    TRACT = "tracts"
    BLOCK_GROUP = "block_groups"
    BLOCK = "blocks"
    PLACE = "places"


CensusYear = Literal[1980, 1990, 2000, 2010, 2020]


@dataclass(frozen=True)
class GeographySelection:
    """One year and kind of geographic unit needed by the run.

    Both population tables and boundary files use this selection. It can describe units to
    analyze, such as 1990 tracts, or units needed to define a study area, such as 2020 counties.

    Attributes:
        census_year (CensusYear): One of 1980, 1990, 2000, 2010, or 2020.
        geography_level (GeographyLevel): Kind of unit whose population and boundaries are needed.
    """

    census_year: CensusYear
    geography_level: GeographyLevel


class StudyAreaType(StrEnum):
    """Ways to choose the enclosing area for each graph.

    COUNTY uses individual counties; CBSA uses entire metropolitan areas. MAX_COUNTY selects the
    most populous county in each metro, and MAX_CITY selects the city with the greatest estimated
    population inside that metro. String values are the names accepted in YAML.
    """

    COUNTY = "county"
    CBSA = "cbsa"
    MAX_COUNTY = "max_county"
    MAX_CITY = "max_city"


class MetroCode(StrEnum):
    """Named CBSA identifiers used in national figure selections and colors."""

    NEW_YORK = "35620"
    LOS_ANGELES = "31080"
    CHICAGO = "16980"
    DALLAS = "19100"
    HOUSTON = "26420"
    WASHINGTON = "47900"
    PHILADELPHIA = "37980"
    MIAMI = "33100"
    ATLANTA = "12060"
    BOSTON = "14460"

    PHOENIX = "38060"
    SAN_ANTONIO = "41700"
    SAN_DIEGO = "41740"
    SAN_JOSE = "41940"
