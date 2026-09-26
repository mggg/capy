"""NHGIS dataset and geography identifiers selected by the replication workflow."""

from enum import StrEnum

from capy_core.geography_types import GeographyLevel


class NhgisDataset(StrEnum):
    """Historical Summary Tape File 1 datasets, using NHGIS's request identifiers."""

    STF1_1980 = "1980_STF1"
    STF1_1990 = "1990_STF1"


class NhgisGeographyLevel(StrEnum):
    """NHGIS identifiers for the requested population geography levels."""

    STATE = "state"
    COUNTY = "county"
    TRACT = "tract"
    BLOCK_GROUP = "blck_grp"
    BLOCK = "block"


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
