"""Shared names for geographic units and the areas used to organize the analysis."""

from enum import StrEnum


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
