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
from .table_columns import CENSUS_POPULATION_COLUMNS, CensusGeographyColumn

# Request the same named count columns that processing uses to derive and check populations.
POPULATION_VARIABLES_BY_YEAR: dict[Literal[2000, 2010, 2020], str] = {
    year: ",".join((CensusGeographyColumn.NAME, *columns.count_columns))
    for (year, dataset), columns in CENSUS_POPULATION_COLUMNS.items()
    if dataset == CensusDataset.PL_94_171
}

# The 2000 block-group source is SF1; its codes differ from PL for the same population groups.
BLOCK_GROUP_VARIABLES_2000 = ",".join(
    (
        CensusGeographyColumn.NAME,
        *CENSUS_POPULATION_COLUMNS[2000, CensusDataset.SUMMARY_FILE_1].count_columns,
    )
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
        file_requests.append(build_census_state_reference_request(directories, year))

    return file_requests


def build_census_state_reference_request(
    directories: RawDataSubdirectories, census_year: Literal[2000, 2010, 2020]
) -> CensusFileRequest:
    """Describe the national PL table used to check a year's statewide population sums.

    Args:
        directories (RawDataSubdirectories): Raw-data subfolders for the run.
        census_year (Literal[2000, 2010, 2020]): Year of the populations being checked.

    Returns:
        CensusFileRequest: State totals with the same eleven population definitions as processing.
    """
    return CensusFileRequest(
        destination_relative_path=f"{directories.population_reference_tables}/{census_year}_states.json",
        census_year=census_year,
        dataset=CensusDataset.PL_94_171,
        variables=POPULATION_VARIABLES_BY_YEAR[census_year],
        geography_level=GeographyLevel.STATE,
    )


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
