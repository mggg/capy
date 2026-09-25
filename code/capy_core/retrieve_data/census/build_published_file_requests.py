"""Editable definitions for TIGER boundaries, original STF1A files, and reference tables."""

from capy_core.geography_types import GeographyLevel, StudyAreaType
from capy_core.pipeline_config import RawDataSubdirectories
from capy_core.retrieve_data.raw_file_requests import (
    GeographyRequest,
    PublicFileRequest,
    RawFileFormat,
)

from ..state_codes import STATE_FIPS_CODES, STF1A_STATE_ABBREVIATIONS


def build_census_published_file_requests(
    directories: RawDataSubdirectories,
    geography_requests: tuple[GeographyRequest, ...],
    study_area_type: StudyAreaType,
) -> list[PublicFileRequest]:
    """Build selected TIGER boundaries and the supporting published data.

    Args:
        directories (RawDataSubdirectories): Folder settings relative to the raw-data root.
        geography_requests (tuple[GeographyRequest, ...]): Shared node and definition selections.
        study_area_type (StudyAreaType): county needs no metro workbook; the other modes require it.

    Returns:
        list[PublicFileRequest]: Boundaries and reference tables, plus original STF1A records for
            1980 tract/BNA matching.
    """
    requests = build_tiger_file_requests(directories, geography_requests)
    if any(
        request.census_year == 1980 and request.geography_level == GeographyLevel.TRACT
        for request in geography_requests
    ):
        # Original records help match 1980 tract/BNA population identities to boundaries. They are
        # published as whole state archives, without a per-level download.
        requests.extend(build_stf1a_file_requests(directories))

    requests.extend(build_reference_file_requests(directories, geography_requests, study_area_type))
    return requests


def build_tiger_file_requests(
    directories: RawDataSubdirectories, geography_requests: tuple[GeographyRequest, ...]
) -> list[PublicFileRequest]:
    """Build selected 2000/2010 boundaries from TIGER2010 and 2020 boundaries from TIGER2020.

    Args:
        directories (RawDataSubdirectories): Folder settings relative to the raw-data root.
        geography_requests (tuple[GeographyRequest, ...]): Shared node and definition selections.

    Returns:
        list[PublicFileRequest]: Selected modern boundaries. Counties use national files; other
            levels use state files. Historical selections are handled by NHGIS.
    """
    geo_product_codes = {
        GeographyLevel.BLOCK_GROUP: "bg",
        GeographyLevel.BLOCK: "tabblock",
        GeographyLevel.COUNTY: "county",
        GeographyLevel.PLACE: "place",
        GeographyLevel.TRACT: "tract",
    }
    selected_pairs = {
        (request.census_year, request.geography_level) for request in geography_requests
    }

    requests = []
    for census_year, geography_level in sorted(selected_pairs):
        if census_year not in (2000, 2010, 2020) or geography_level not in geo_product_codes:
            continue
        if geography_level == GeographyLevel.PLACE and census_year != 2020:
            continue

        geo_product_code = geo_product_codes[geography_level]
        if census_year == 2020 and geography_level == GeographyLevel.BLOCK:
            geo_product_code = "tabblock20"

        area_codes = ("us",) if geography_level == GeographyLevel.COUNTY else STATE_FIPS_CODES
        for area_code in area_codes:
            if census_year == 2020:
                filename = f"tl_2020_{area_code}_{geo_product_code}.zip"
                url = f"https://www2.census.gov/geo/tiger/TIGER2020/{geo_product_code.upper()}/{filename}"
            else:
                # NOTE: TIGER2010 is the source release contains the shapefiles for 2010 and 2000.
                # TIGER was not an official format until...
                filename = f"tl_2010_{area_code}_{geo_product_code}{str(census_year)[-2:]}.zip"
                url = f"https://www2.census.gov/geo/tiger/TIGER2010/{geo_product_code.upper()}/{census_year}/{filename}"

            requests.append(
                PublicFileRequest(
                    destination_relative_path=(
                        f"{directories.census_boundary_files}/{census_year}/"
                        f"{geography_level.value}/{filename}"
                    ),
                    file_format=RawFileFormat.SHAPEFILE_ZIP,
                    url=url,
                )
            )

    return requests


def build_stf1a_file_requests(directories: RawDataSubdirectories) -> list[PublicFileRequest]:
    """Request original 1980 STF1A archives for the 50 states and DC."""
    return [
        PublicFileRequest(
            destination_relative_path=f"{directories.original_1980_population_tables}/stf1ax{state}.zip",
            file_format=RawFileFormat.ZIP_ARCHIVE,
            url=f"https://www2.census.gov/census_1980/stf1a/stf1ax{state}.zip",
        )
        for state in STF1A_STATE_ABBREVIATIONS
    ]


def build_reference_file_requests(
    directories: RawDataSubdirectories,
    geography_requests: tuple[GeographyRequest, ...],
    study_area_type: StudyAreaType,
) -> list[PublicFileRequest]:
    """Request population reference tables and, for metro-based modes, the March 2020 workbook.

    Args:
        directories (RawDataSubdirectories): Folder settings relative to the raw-data root.
        geography_requests (tuple[GeographyRequest, ...]): Required years, including definition
            data.
        study_area_type (StudyAreaType): county omits the workbook; all other supported modes
            include it.

    Returns:
        list[PublicFileRequest]: National totals, historical race totals when needed, and any metro
            workbook. Each reference file retains its complete published contents.
    """
    years = {request.census_year for request in geography_requests}
    requests = []
    if 2000 in years or 2010 in years or 2020 in years:
        # The 2020 release also contains state resident-population totals for earlier years.
        requests.append(
            PublicFileRequest(
                destination_relative_path=(
                    f"{directories.population_reference_tables}/census_state_population_totals_2020_release.csv"
                ),
                file_format=RawFileFormat.CSV,
                url="https://www2.census.gov/programs-surveys/decennial/2020/data/apportionment/apportionment.csv",
            )
        )

    if study_area_type != StudyAreaType.COUNTY:
        # NOTE: Metro membership stays fixed at March 2020 across population years.
        # Changing study_area_vintage changes boundary inputs, not this county membership list.
        requests.append(
            PublicFileRequest(
                destination_relative_path=f"{directories.metro_membership_tables}/list1_march_2020.xls",
                file_format=RawFileFormat.EXCEL_XLS,
                url="https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2020/delineation-files/list1_2020.xls",
            )
        )

    # A tables summarize race and Hispanic origin; E tables cross race with Hispanic origin.
    table_numbers_by_year = {1980: ("tableA-03", "tableE-03"), 1990: ("tableA-01", "tableE-01")}
    for year in sorted(years & table_numbers_by_year.keys()):
        for table_name in table_numbers_by_year[year]:
            requests.append(
                PublicFileRequest(
                    destination_relative_path=(
                        f"{directories.population_reference_tables}/"
                        f"census_working_paper_56_{year}_{table_name}.xlsx"
                    ),
                    file_format=RawFileFormat.EXCEL_XLSX,
                    url=f"https://www2.census.gov/library/working-papers/2002/demo/pop-twps0056/{table_name}.xlsx",
                )
            )

    return requests
