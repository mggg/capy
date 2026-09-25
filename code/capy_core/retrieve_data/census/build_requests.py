"""Build Census input selections, population queries, and their local table filenames."""

from typing import Literal

from capy_core.geography_types import GeographyLevel, StudyAreaType
from capy_core.pipeline_config import RawDataSubdirectories
from capy_core.retrieve_data.raw_file_requests import (
    CensusDataset,
    CensusFileRequest,
    GeographyRequest,
    PublicFileRequest,
)

from ..state_codes import STATE_FIPS_CODES
from .build_published_file_requests import build_census_published_file_requests

# NOTE: The study uses non-Hispanic White-alone and Black-alone counts for modern years.
# POC means total population minus non-Hispanic White, not just Black. The additional race and
# Hispanic-origin columns support checks of those population definitions. Each quoted piece names
# one requested column; Python joins adjacent strings into the comma-separated list sent as the
# Census API's get parameter. See the variable guide in documentation/raw_source_acquisition.md
# for table definitions and the cross-year mapping.
POPULATION_VARIABLES_BY_YEAR: dict[Literal[2000, 2010, 2020], str] = {
    2000: (
        "NAME,"  # Geographic area's display name.
        "PL001001,"  # Total population, all ages.
        "PL001003,"  # White alone, including Hispanic residents.
        "PL001004,"  # Black or African American alone, including Hispanic residents.
        "PL001005,"  # American Indian and Alaska Native alone, including Hispanic residents.
        "PL001006,"  # Asian alone, including Hispanic residents.
        "PL001007,"  # Native Hawaiian and Other Pacific Islander alone, including Hispanic residents.
        "PL001008,"  # Some other race alone, including Hispanic residents.
        "PL001009,"  # Two or more races, including Hispanic residents.
        "PL002002,"  # Hispanic or Latino, of any race.
        "PL002005,"  # Non-Hispanic White alone: the study's WHITE count.
        "PL002006"  # Non-Hispanic Black or African American alone: the study's BLACK count.
    ),
    2010: (
        "NAME,"  # Geographic area's display name.
        "P001001,"  # Total population, all ages.
        "P001003,"  # White alone, including Hispanic residents.
        "P001004,"  # Black or African American alone, including Hispanic residents.
        "P001005,"  # American Indian and Alaska Native alone, including Hispanic residents.
        "P001006,"  # Asian alone, including Hispanic residents.
        "P001007,"  # Native Hawaiian and Other Pacific Islander alone, including Hispanic residents.
        "P001008,"  # Some other race alone, including Hispanic residents.
        "P001009,"  # Two or more races, including Hispanic residents.
        "P002002,"  # Hispanic or Latino, of any race.
        "P002005,"  # Non-Hispanic White alone: the study's WHITE count.
        "P002006"  # Non-Hispanic Black or African American alone: the study's BLACK count.
    ),
    2020: (
        "NAME,"  # Geographic area's display name.
        "P1_001N,"  # Total population, all ages.
        "P1_003N,"  # White alone, including Hispanic residents.
        "P1_004N,"  # Black or African American alone, including Hispanic residents.
        "P1_005N,"  # American Indian and Alaska Native alone, including Hispanic residents.
        "P1_006N,"  # Asian alone, including Hispanic residents.
        "P1_007N,"  # Native Hawaiian and Other Pacific Islander alone, including Hispanic residents.
        "P1_008N,"  # Some other race alone, including Hispanic residents.
        "P1_009N,"  # Two or more races, including Hispanic residents.
        "P2_002N,"  # Hispanic or Latino, of any race.
        "P2_005N,"  # Non-Hispanic White alone: the study's WHITE count.
        "P2_006N"  # Non-Hispanic Black or African American alone: the study's BLACK count.
    ),
}

# NOTE: The selected source for 2000 block groups is SF1. Its column codes differ from PL,
# so switching the dataset also requires switching variables to preserve the definitions above.
BLOCK_GROUP_VARIABLES_2000 = (
    "NAME,"  # Geographic area's display name.
    "P001001,"  # Total population, all ages.
    "P003003,"  # White alone, including Hispanic residents.
    "P003004,"  # Black or African American alone, including Hispanic residents.
    "P003005,"  # American Indian and Alaska Native alone, including Hispanic residents.
    "P003006,"  # Asian alone, including Hispanic residents.
    "P003007,"  # Native Hawaiian and Other Pacific Islander alone, including Hispanic residents.
    "P003008,"  # Some other race alone, including Hispanic residents.
    "P003009,"  # Two or more races, including Hispanic residents.
    "P004002,"  # Hispanic or Latino, of any race.
    "P004005,"  # Non-Hispanic White alone: the study's WHITE count.
    "P004006"  # Non-Hispanic Black or African American alone: the study's BLACK count.
)


def build_census_file_requests(
    directories: RawDataSubdirectories,
    geography_requests: tuple[GeographyRequest, ...],
    study_area_type: StudyAreaType,
) -> list[CensusFileRequest | PublicFileRequest]:
    """List Census population tables, boundary archives, and supporting reference files.

    Args:
        directories (RawDataSubdirectories): Folder settings beneath the raw-data directory.
        geography_requests (tuple[GeographyRequest, ...]): Years and levels needed by the run.
        study_area_type (StudyAreaType): County runs omit the metro membership workbook.

    Returns:
        list[CensusFileRequest | PublicFileRequest]: Census population inputs followed by
            published files. The combined Census/NHGIS input list is sorted by its caller. This
            describes downloads without reading files or contacting the Census Bureau.
    """
    requests: list[CensusFileRequest | PublicFileRequest] = [
        *build_census_population_requests(directories, geography_requests),
        *build_census_published_file_requests(directories, geography_requests, study_area_type),
    ]
    return requests


def build_census_population_requests(
    directories: RawDataSubdirectories, geography_requests: tuple[GeographyRequest, ...]
) -> list[CensusFileRequest]:
    """List the modern population tables and state totals needed by the run.

    Requests the selected modern geographies for the 50 states, DC, and Puerto Rico. Each required
    modern year also gets one national table of state totals, which can be used to check the
    population sums later. This builds requests without reading or downloading files.

    Args:
        directories (RawDataSubdirectories): Folder settings relative to the raw-data root.
        geography_requests (tuple[GeographyRequest, ...]): Years and levels needed for the
            analysis and its enclosing areas. The boundary builder receives the same selections.

    Returns:
        list[CensusFileRequest]: Selected statewide population files and state-total files.
    """
    file_requests = []
    for year, variables in POPULATION_VARIABLES_BY_YEAR.items():
        levels: tuple[GeographyLevel, ...] = tuple(
            request.geography_level for request in geography_requests if request.census_year == year
        )
        if not levels:
            continue

        file_requests.extend(
            build_statewide_population_requests(year, variables, levels, directories)
        )
        # NOTE: State totals provide a separate aggregation for population checks, not another
        # graph resolution or an independent enumeration. Places do not partition a state.
        file_requests.append(
            CensusFileRequest(
                destination_relative_path=f"{directories.population_reference_tables}/{year}_states.json",
                census_year=year,
                dataset=CensusDataset.PL_94_171,
                variables=variables,
                geography_level=GeographyLevel.STATE,
            )
        )

    return file_requests


def build_statewide_population_requests(
    year: Literal[2000, 2010, 2020],
    variables: str,
    geography_levels: tuple[GeographyLevel, ...],
    directories: RawDataSubdirectories,
) -> list[CensusFileRequest]:
    """Describe selected population tables for a Census year, one per state and geographic level.

    Args:
        directories (RawDataSubdirectories): Folder settings relative to the raw-data root.
        year (int): Census year: 2000, 2010, or 2020.
        geography_levels (tuple[GeographyLevel, ...]): Shared selected levels for this year.
        variables (str): Comma-separated PL 94-171 variables. The 2000 block-group requests
            substitute SF1 variables and dataset.

    Returns:
        list[CensusFileRequest]: One population-table request per state and selected level.
            Retrieval may first need county tables to form a 2010 block query.
    """
    file_requests = []
    for geography_level in geography_levels:
        dataset = CensusDataset.PL_94_171
        requested_variables = variables
        if year == 2000 and geography_level == GeographyLevel.BLOCK_GROUP:
            dataset = CensusDataset.SUMMARY_FILE_1
            requested_variables = BLOCK_GROUP_VARIABLES_2000

        for state_code in STATE_FIPS_CODES:
            file_requests.append(
                CensusFileRequest(
                    destination_relative_path=build_census_table_relative_path(
                        directories, year, geography_level, state_code
                    ),
                    census_year=year,
                    dataset=dataset,
                    variables=requested_variables,
                    geography_level=geography_level,
                    state_code=state_code,
                )
            )

    return file_requests


def build_census_table_relative_path(
    directories: RawDataSubdirectories,
    year: int,
    geography_level: GeographyLevel,
    state_code: str,
) -> str:
    """Return where a state's population table belongs inside the raw-data directory.

    Args:
        directories (RawDataSubdirectories): Folder settings beneath the raw-data directory.
        year (int): Census year.
        geography_level (GeographyLevel): County, tract, block group, block, or place.
        state_code (str): Two-digit state FIPS code.

    Returns:
        str: Relative filename, such as census/2020/tracts/10/state.json. No file is opened.

    Raises:
        ValueError: National state totals belong in population_reference_tables instead.
    """
    if geography_level == GeographyLevel.STATE:
        raise ValueError("State totals belong with the population reference tables")

    return (
        f"{directories.census_population_tables}/{year}/"
        f"{geography_level.value}/{state_code}/state.json"
    )
