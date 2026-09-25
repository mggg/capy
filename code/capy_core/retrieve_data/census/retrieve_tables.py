"""Resolve Census county prerequisites and acquire PL 94-171 and SF1 population tables.

Census API request syntax and geographic filters:
https://www.census.gov/data/developers/guidance/api-user-guide.html
"""

import os
from dataclasses import replace
from pathlib import Path

from capy_core.geography_types import GeographyLevel

from ..check_raw_files import load_census_table
from ..http_transport import download_file
from ..raw_file_requests import CensusFileRequest, RawFileRequest
from ..retrieval_config import RawDataSubdirectories
from ..stage_files import StagedFile
from .build_requests import build_census_table_relative_path


def prepare_download_batches_with_2010_counties_first(
    requests: list[RawFileRequest],
    raw_data_directory: Path,
    directories: RawDataSubdirectories,
) -> list[list[RawFileRequest]]:
    """Put needed 2010 county tables in a batch before the selected block tables.

    This function must be called before download_census_table() when downloading 2010 data because
    the block queries for 2010 do not work with wildcard query parameters.

    Args:
        requests (list[RawFileRequest]): Selected raw inputs with unique destinations.
        raw_data_directory (Path): Used to identify existing block files that need no download.
        directories (RawDataSubdirectories): Configured folders beneath raw_data_directory.

    Returns:
        list[list[RawFileRequest]]: Nonempty batches to execute in order. Each destination occurs
            once, including added county tables. Existing block files add no prerequisites. Checks
            file existence, but does not read contents or download.

    Raises:
        ValueError: A selected input conflicts with a required county-table definition.
    """
    selected_by_path = {request.destination_relative_path: request for request in requests}
    counties_by_path: dict[str, RawFileRequest] = {}

    for request in requests:
        if not isinstance(request, CensusFileRequest):
            continue
        if request.census_year != 2010 or request.geography_level != GeographyLevel.BLOCK:
            continue

        if (raw_data_directory / request.destination_relative_path).exists():
            continue

        assert request.state_code is not None

        county_request = replace(
            request,
            destination_relative_path=build_census_table_relative_path(
                directories, 2010, GeographyLevel.COUNTY, request.state_code
            ),
            geography_level=GeographyLevel.COUNTY,
        )
        county_path = county_request.destination_relative_path

        existing_request = selected_by_path.get(county_path, counties_by_path.get(county_path))

        if existing_request is not None and existing_request != county_request:
            raise ValueError(f"Conflicting Census county prerequisite: {county_path}")

        counties_by_path[county_path] = county_request

    remaining = [
        request for request in requests if request.destination_relative_path not in counties_by_path
    ]

    batches = []
    if counties_by_path:
        batches.append(list(counties_by_path.values()))
    if remaining:
        batches.append(remaining)

    return batches


def download_census_table(
    request: CensusFileRequest,
    destination: StagedFile,
    raw_data_directory: Path,
    directories: RawDataSubdirectories,
) -> None:
    """Request Census data and stage the response without changing its JSON formatting.

    County tables must already be available for 2010 block queries.
    prepare_download_batches_with_2010_counties_first() places those downloads before the
    dependent block downloads. CENSUS_API_KEY is read from the environment if present and is not
    saved. The caller checks the saved table and publishes the completed file.

    Args:
        request (CensusFileRequest): Census year, dataset, variables, and geographic selection.
        destination (StagedFile): Empty file owned by the caller's staging context.
        raw_data_directory (Path): Contains county tables needed by 2010 block queries.
        directories (RawDataSubdirectories): Configured folders beneath raw_data_directory.

    Raises:
        DataProviderError: Transport fails or the response fails the download's byte-count check.
        ValueError: A county prerequisite is invalid, or staging is not empty.
        OSError: Reading a county prerequisite or writing the staged file fails.
    """
    parameters = resolve_census_query_parameters(request, raw_data_directory, directories)
    if api_key := os.environ.get("CENSUS_API_KEY"):
        parameters["key"] = api_key

    url = f"https://api.census.gov/data/{request.census_year}/dec/{request.dataset.value}"
    download_file(
        url, destination, parameters=parameters, download_label=request.destination_relative_path
    )


def resolve_census_query_parameters(
    request: CensusFileRequest, raw_data_directory: Path, directories: RawDataSubdirectories
) -> dict[str, str]:
    """Translate a Census selection to get/for/in parameters, resolving 2010 county codes.

    Args:
        request (CensusFileRequest): Year, dataset, variables, and requested geography.
        raw_data_directory (Path): Contains any prerequisite 2010 county table.
        directories (RawDataSubdirectories): Configured folders beneath raw_data_directory.

    Returns:
        dict[str, str]: Query parameters without credentials.

    Raises:
        OSError: A needed county table is missing or unreadable.
        ValueError: A county table is malformed or contains invalid county codes.
    """
    census_geography_names = {
        GeographyLevel.STATE: "state",
        GeographyLevel.COUNTY: "county",
        GeographyLevel.TRACT: "tract",
        GeographyLevel.BLOCK_GROUP: "block group",
        GeographyLevel.BLOCK: "block",
        GeographyLevel.PLACE: "place",
    }
    geography_name = census_geography_names[request.geography_level]
    parameters = {"get": request.variables, "for": f"{geography_name}:*"}

    if request.state_code is None:
        return parameters

    parent_geography = f"state:{request.state_code}"

    if request.geography_level in (
        GeographyLevel.TRACT,
        GeographyLevel.BLOCK_GROUP,
        GeographyLevel.BLOCK,
    ):
        if request.census_year == 2010 and request.geography_level == GeographyLevel.BLOCK:
            # NOTE: For 2010 PL block queries, county:* can return HTTP 204 (no rows).
            # List counties from the 2010 table to cover the state using that year's codes.
            # Documented query forms: https://api.census.gov/data/2010/dec/pl/examples.html
            county_path = raw_data_directory / build_census_table_relative_path(
                directories, 2010, GeographyLevel.COUNTY, request.state_code
            )
            county_codes = load_county_codes(county_path, request.state_code)
            parent_geography += f" county:{','.join(county_codes)}"

        else:
            parent_geography += " county:*"

    if request.geography_level in (GeographyLevel.BLOCK_GROUP, GeographyLevel.BLOCK):
        parent_geography += " tract:*"

    parameters["in"] = parent_geography
    return parameters


def load_county_codes(county_table_path: Path, state_code: str) -> tuple[str, ...]:
    """Read county identifiers from a retrieved Census county table for one state.

    Args:
        county_table_path (Path): Saved Census API JSON response, including its header row.
        state_code (str): Two-digit state FIPS code expected in every row.

    Returns:
        tuple[str, ...]: Unique three-digit county codes in sorted order.

    Raises:
        OSError: The county table cannot be read.
        ValueError: The table is malformed, empty, repeats counties, or contains another state.
    """
    header, *rows = load_census_table(county_table_path)
    state_column = header.index("state")
    county_column = header.index("county")

    county_codes = []
    for row in rows:
        county_code = row[county_column]

        if row[state_column] != state_code:
            raise ValueError(f"County table contains a different state: {county_table_path}")

        if not isinstance(county_code, str) or len(county_code) != 3 or not county_code.isdecimal():
            raise ValueError(f"County table contains an invalid county code: {county_table_path}")

        county_codes.append(county_code)

    if len(set(county_codes)) != len(county_codes):
        raise ValueError(f"County table repeats county codes: {county_table_path}")

    return tuple(sorted(county_codes))
