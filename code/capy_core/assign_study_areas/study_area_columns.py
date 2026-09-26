"""Shared column labels for study-area definitions, selection, and membership accounting."""

from enum import StrEnum


class StudyAreaColumn(StrEnum):
    """Area identities and definition fields, reused wherever those areas are referenced.

    COUNTY_CODE is a full five-digit county identifier, unlike the three-digit county component
    in GeographyColumn.COUNTY_CODE. COUNTY_CODES lists counties intersecting the selected area;
    METRO_COUNTY_CODES retains the selecting metro's full county roster.
    """

    STUDY_AREA_ID = "study_area_id"
    STUDY_AREA_TYPE = "study_area_type"
    DEFINITION_YEAR = "definition_year"
    NAME = "name"
    METRO_CODE = "metro_code"
    METRO_NAME = "metro_name"
    COUNTY_CODE = "county_code"
    COUNTY_CODES = "county_codes"
    METRO_COUNTY_CODES = "metro_county_codes"
    SELECTED_COUNTY_CODE = "selected_county_code"
    SELECTED_PLACE_CODE = "selected_place_code"
    DEFINITION_POPULATION = "definition_population"


class SelectionColumn(StrEnum):
    """Candidate identities, population estimates, and the recorded selection decision.

    Block counts support city population estimates. POPULATION_INSIDE_METRO counts residents
    within the candidate city and selecting metro; CITY_POPULATION covers the whole city.
    Shared metro and county identifiers use StudyAreaColumn rather than being repeated here.
    """

    PLACE_CODE = "place_code"
    PLACE_NAME = "place_name"
    BLOCK_CODE = "block_code"
    BLOCK_POPULATION = "block_population"
    CITY_POPULATION = "city_population"
    POPULATION_INSIDE_METRO = "population_inside_metro"
    AREA_INSIDE_METRO_KM2 = "area_inside_metro_km2"
    CITY_AREA_KM2 = "city_area_km2"
    SELECTED = "selected"
    SELECTION_REASON = "selection_reason"


class MembershipColumn(StrEnum):
    """Selected-unit counts, source paths, and per-area membership outcomes.

    CENSUS_YEAR and GEOGRAPHY_LEVEL describe the selected units, not the fixed definition vintage.
    Their lowercase labels belong to the membership summary; the upstream population tables
    retain their existing uppercase labels. GEOGRAPHY_FILE is relative to the joined-data root.
    """

    UNIT_COUNT = "unit_count"
    STATUS = "status"
    GEOGRAPHY_FILE = "geography_file"
    CENSUS_YEAR = "census_year"
    GEOGRAPHY_LEVEL = "geography_level"
