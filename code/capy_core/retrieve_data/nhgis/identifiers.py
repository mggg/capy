"""NHGIS dataset and geography identifiers selected by the replication workflow."""

from enum import StrEnum

from capy_core.geography_types import GeographyLevel


class NhgisDataset(StrEnum):
    """Historical Summary Tape File 1 datasets, using NHGIS's request identifiers."""

    STF1_1980 = "1980_STF1"
    STF1_1990 = "1990_STF1"


class NhgisGeographyLevel(StrEnum):
    """NHGIS request levels, including the 1980 geographic correspondence tables.

    The diagnostic hierarchies follow the downloaded codebooks. SMSA means Standard Metropolitan
    Statistical Area. Tract/BNA and enumeration-district hierarchies start with state, SMSA, and
    county, then split by the named subdivisions and places. They describe overlapping parts,
    unlike the five whole-area population levels mapped below.
    """

    STATE = "state"
    COUNTY = "county"
    TRACT = "tract"
    BLOCK_GROUP = "blck_grp"
    BLOCK = "block"

    TRACT_BY_COUNTY_SUBDIVISION_PLACE_REMAINDER = "tract_080"
    TRACT_BNA_BY_SMSA_COUNTY_SUBDIVISION_PLACE = "tract_02098"
    TRACT_BNA_BY_SMSA_PLACE = "tract_02498"
    ENUMERATION_DISTRICT_BY_SMSA_COUNTY_SUBDIVISION_PLACE_TRACT_BNA = "enumdist_02298"
    ENUMERATION_DISTRICT_BY_SMSA_PLACE_TRACT_BNA = "enumdist_02698"
    PLACE_REMAINDER_BY_COUNTY_SUBDIVISION = "place_070"


NHGIS_DATASETS_BY_YEAR = {
    1980: NhgisDataset.STF1_1980,
    1990: NhgisDataset.STF1_1990,
}
NHGIS_LEVELS_BY_GEOGRAPHY = {
    GeographyLevel.STATE: NhgisGeographyLevel.STATE,
    GeographyLevel.COUNTY: NhgisGeographyLevel.COUNTY,
    GeographyLevel.TRACT: NhgisGeographyLevel.TRACT,
    GeographyLevel.BLOCK_GROUP: NhgisGeographyLevel.BLOCK_GROUP,
    GeographyLevel.BLOCK: NhgisGeographyLevel.BLOCK,
}
