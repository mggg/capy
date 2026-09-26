"""Editable NHGIS population and boundary extract definitions."""

from capy_core.geography_types import GeographyLevel
from capy_core.pipeline_config import RawDataSubdirectories
from capy_core.retrieve_data.raw_file_requests import (
    GeographyRequest,
    NhgisBoundaryFileRequest,
    NhgisTableFileRequest,
)

from ..state_codes import STATE_FIPS_CODES
from .identifiers import (
    NHGIS_DATASETS_BY_YEAR,
    NHGIS_LEVELS_BY_GEOGRAPHY,
    NhgisDataset,
    NhgisGeographyLevel,
)

# NOTE: NT7 supplies race counts and NT9B supplies Spanish-origin race counts, allowing
# non-Hispanic White and Black counts to be derived. NT1A and NT9A supply totals for checks.
POPULATION_TABLES_1980 = ("NT1A", "NT7", "NT9A", "NT9B")

# NOTE: Retain both whole-area and urban/rural detail for geographic correspondence checks.
# Urban and rural are components; do not add a whole-area total to its component counts.
# Source: NHGIS 1980_STF1 metadata, breakdowns[bs03].breakdownValues, and extract codebooks.
# See documentation/raw_source_acquisition.md#nhgis-1980-geographic-subareas for more information.
TOTAL_AND_SUBAREA_BREAKDOWNS_1980 = ("bs03.ge0000", "bs03.ge0100", "bs03.ge0800")


def build_nhgis_file_requests(
    directories: RawDataSubdirectories, geography_requests: tuple[GeographyRequest, ...]
) -> list[NhgisBoundaryFileRequest | NhgisTableFileRequest]:
    """List historical boundary files and population archives needed by the run.

    County files use NHGIS products based on TIGER 2008; smaller units use products based on TIGER
    2000. These product years describe the boundary source, not the population year. The 1990
    block archive covers the states and DC, excluding Puerto Rico.

    Each selected population level has its own archive. State totals support population checks;
    boundary files follow the selected levels. No downloads start here.

    Args:
        directories (RawDataSubdirectories): Folder settings relative to the raw-data root.
        geography_requests (tuple[GeographyRequest, ...]): Years and levels needed for the
            analysis and the areas enclosing it. The modern Census builder uses the same list.

    Returns:
        list[NhgisBoundaryFileRequest | NhgisTableFileRequest]: Selected historical population
            and boundary inputs.
    """
    boundary_products = {
        (1980, GeographyLevel.COUNTY): "us_county_1980_tl2008",
        (1980, GeographyLevel.TRACT): "us_tract_1980_tl2000",
        (1990, GeographyLevel.COUNTY): "us_county_1990_tl2008",
        (1990, GeographyLevel.TRACT): "us_tract_1990_tl2000",
        (1990, GeographyLevel.BLOCK_GROUP): "us_blck_grp_1990_tl2000",
    }
    requests: list[NhgisBoundaryFileRequest | NhgisTableFileRequest] = []
    for selection in geography_requests:
        year, level = selection.census_year, selection.geography_level
        if year not in (1980, 1990):
            continue

        if (year, level) == (1990, GeographyLevel.BLOCK):
            # NOTE: Puerto Rico is outside the supported historical boundary collection
            shapefiles = tuple(
                f"{state_code}0_block_1990_tl2000"
                for state_code in STATE_FIPS_CODES
                if state_code != "72"
            )
        else:
            shapefiles = (boundary_products[year, level],)

        requests.append(
            NhgisBoundaryFileRequest(
                destination_relative_path=(
                    f"{directories.nhgis_population_and_boundaries}/{year}/{level.value}/boundaries.zip"
                ),
                shapefiles=shapefiles,
            )
        )

    requests.extend(build_historical_population_requests(directories, geography_requests))

    return requests


def build_historical_population_requests(
    directories: RawDataSubdirectories, geography_requests: tuple[GeographyRequest, ...]
) -> list[NhgisTableFileRequest]:
    """Request selected historical population levels, plus state totals for checking their sums.

    Each archive contains one level, so a tract run can reuse its table in a later block-and-tract
    run. The directory identifies both year and level; changing the selection never changes the
    contents associated with an existing filename.

    Args:
        directories (RawDataSubdirectories): Folder settings relative to the raw-data root.
        geography_requests (tuple[GeographyRequest, ...]): Node and study-area inputs needed.

    Returns:
        list[NhgisTableFileRequest]: One archive per required historical year and population
            level.
    """
    requests = []
    for year in (1980, 1990):
        levels = {
            selection.geography_level
            for selection in geography_requests
            if selection.census_year == year
        }

        if not levels:
            continue

        levels.add(GeographyLevel.STATE)
        for level in sorted(levels):
            requests.append(
                build_table_request(
                    directories,
                    f"{year}/{level.value}/population.zip",
                    dataset_name=NHGIS_DATASETS_BY_YEAR[year],
                    tables=POPULATION_TABLES_1980 if year == 1980 else ("NP1", "NP10"),
                    geographic_levels=(NHGIS_LEVELS_BY_GEOGRAPHY[level],),
                    breakdowns=TOTAL_AND_SUBAREA_BREAKDOWNS_1980 if year == 1980 else (),
                )
            )

    return requests


def build_table_request(
    directories: RawDataSubdirectories,
    archive_name: str,
    *,
    dataset_name: NhgisDataset,
    tables: tuple[str, ...],
    geographic_levels: tuple[NhgisGeographyLevel, ...],
    breakdowns: tuple[str, ...] = (),
) -> NhgisTableFileRequest:
    """Build an NHGIS table download using CSV headers and a single-file layout.

    Args:
        directories (RawDataSubdirectories): Folder settings relative to the raw-data root.
        archive_name (str): ZIP path within the NHGIS folder, grouped by year and level.
        dataset_name (NhgisDataset): Fixed-year dataset identifier, such as 1980_STF1.
        tables (tuple[str, ...]): NHGIS table identifiers within the dataset.
        geographic_levels (tuple[NhgisGeographyLevel, ...]): Geographic level codes to include.
        breakdowns (tuple[str, ...]): Codes selecting the whole area or parts such as urban areas.
            Empty uses the dataset's default selection.

    Returns:
        NhgisTableFileRequest: Population table selections.
    """
    return NhgisTableFileRequest(
        destination_relative_path=f"{directories.nhgis_population_and_boundaries}/{archive_name}",
        dataset_name=dataset_name,
        tables=tables,
        geographic_levels=geographic_levels,
        breakdowns=breakdowns,
        description=f"Capy replication: {archive_name.removesuffix('.zip')}",
    )
