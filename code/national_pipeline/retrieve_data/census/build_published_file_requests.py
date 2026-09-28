"""Editable definitions for TIGER boundaries and published reference tables."""

from national_pipeline.geography_types import GeographyLevel, StudyAreaType
from national_pipeline.pipeline_config import RawDataSubdirectories
from national_pipeline.retrieve_data.raw_file_requests import (
    GeographyRequest,
    PublicFileRequest,
    RawFileFormat,
    TigerBoundaryFileRequest,
)

from ..state_codes import STATE_FIPS_CODES

# Whole STF1B discs and supplemental PL tables used to identify empty 1990 blocks.
STF1B_1990_ARCHIVE_FILENAMES = tuple(f"disc{disc_number}.zip" for disc_number in range(1, 11))
PL_1990_REFERENCE_FILENAMES = {"06": "pl9417ca.dbf", "09": "pl9417ct.dbf"}

METRO_MEMBERSHIP_FILENAME = "list1_march_2020.xls"
CENSUS_RESIDENT_TOTALS_FILENAME = "census_state_population_totals_2020_release.csv"

# E tables cross race with Hispanic origin and supply the study's state comparisons.
HISTORICAL_STUDY_TOTALS_SOURCE_FILENAMES = {1980: "tableE-03.xlsx", 1990: "tableE-01.xlsx"}
HISTORICAL_STUDY_TOTALS_FILENAMES = {
    year: f"census_working_paper_56_{year}_{source_filename}"
    for year, source_filename in HISTORICAL_STUDY_TOTALS_SOURCE_FILENAMES.items()
}

RACE_TOTALS_1980_SOURCE_FILENAME = "tableA-03.xlsx"
RACE_TOTALS_1980_FILENAME = f"census_working_paper_56_1980_{RACE_TOTALS_1980_SOURCE_FILENAME}"

# These counties contain the twelve 1980 BNAs absent from the NHGIS tract/BNA product.
MISSING_1980_BNAS_BY_COUNTY = {
    "12107": ("9901", "9902", "9903"),
    "38033": ("9901",),
    "40023": ("9901", "9902"),
    "49021": ("9901", "9902"),
    "49025": ("9901", "9902", "9903", "9904"),
}


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
        list[PublicFileRequest]: Boundaries and reference tables needed for population checks
            and joins.
    """
    requests: list[PublicFileRequest] = list(
        build_tiger_file_requests(directories, geography_requests)
    )

    if any(
        request.census_year == 1980 and request.geography_level == GeographyLevel.TRACT
        for request in geography_requests
    ):
        requests.extend(
            PublicFileRequest(
                destination_relative_path=(
                    f"{directories.original_1980_boundary_files}/{county_code}.zip"
                ),
                file_format=RawFileFormat.ZIP_ARCHIVE,
                url=f"https://www2.census.gov/geo/tiger/TIGER1992/{county_code[:2]}/{county_code}.zip",
            )
            for county_code in MISSING_1980_BNAS_BY_COUNTY
        )

    requests.extend(build_reference_file_requests(directories, geography_requests, study_area_type))

    if any(
        request.census_year == 1990 and request.geography_level == GeographyLevel.BLOCK
        for request in geography_requests
    ):
        requests.extend(build_1990_block_reference_requests(directories))

    return requests


def build_1990_block_reference_requests(
    directories: RawDataSubdirectories,
) -> list[PublicFileRequest]:
    """Request original tables that establish which unmatched 1990 land blocks are empty.

    STF1B zero-population tables are published in ten whole disc archives. Two PL tables supply
    additional California and Connecticut records absent from those zero-population tables.

    Args:
        directories (RawDataSubdirectories): Configured raw-data subfolders.

    Returns:
        list[PublicFileRequest]: Ten unchanged ZIP archives and two unchanged dBase tables.
    """
    directory = directories.original_1990_block_references
    requests = [
        PublicFileRequest(
            destination_relative_path=f"{directory}/{filename}",
            file_format=RawFileFormat.ZIP_ARCHIVE,
            url=f"https://www2.census.gov/census_1990/stf1b/{filename}",
        )
        for filename in STF1B_1990_ARCHIVE_FILENAMES
    ]

    source_directories_by_state = {
        "06": "CD7%20-%20CA%20NY",
        "09": "CD5%20-%20CT%20DC%20MD%20NC%20OH%20RI",
    }

    for state_code, filename in PL_1990_REFERENCE_FILENAMES.items():
        source_directory = source_directories_by_state[state_code]
        requests.append(
            PublicFileRequest(
                destination_relative_path=f"{directory}/{filename}",
                file_format=RawFileFormat.DBASE_TABLE,
                url=f"https://www2.census.gov/census_1990/1990_PL94-171/{source_directory}/{filename}",
            )
        )

    return requests


def build_tiger_file_requests(
    directories: RawDataSubdirectories, geography_requests: tuple[GeographyRequest, ...]
) -> list[TigerBoundaryFileRequest]:
    """Build selected 2000/2010 boundaries from TIGER2010 and 2020 boundaries from TIGER2020.

    Args:
        directories (RawDataSubdirectories): Folder settings relative to the raw-data root.
        geography_requests (tuple[GeographyRequest, ...]): Shared node and definition selections.

    Returns:
        list[TigerBoundaryFileRequest]: Selected modern boundaries. Counties use national files; other
            levels use state files. Historical selections are handled by NHGIS.
    """
    geo_product_codes = {
        GeographyLevel.BLOCK_GROUP: "bg",
        GeographyLevel.BLOCK: "tabblock",
        GeographyLevel.COUNTY: "county",
        GeographyLevel.PLACE: "place",
        GeographyLevel.TRACT: "tract",
    }
    selected_years_and_levels = {
        (request.census_year, request.geography_level) for request in geography_requests
    }

    requests = []

    for census_year, geography_level in sorted(selected_years_and_levels):
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
                # NOTE: TIGER2010 supplies both 2000 and 2010 geography in this collection.
                filename = f"tl_2010_{area_code}_{geo_product_code}{str(census_year)[-2:]}.zip"
                url = f"https://www2.census.gov/geo/tiger/TIGER2010/{geo_product_code.upper()}/{census_year}/{filename}"

            requests.append(
                TigerBoundaryFileRequest(
                    census_year=census_year,
                    geography_level=geography_level,
                    state_code=None if area_code == "us" else area_code,
                    destination_relative_path=(
                        f"{directories.census_boundary_files}/{census_year}/"
                        f"{geography_level.value}/{filename}"
                    ),
                    file_format=RawFileFormat.SHAPEFILE_ZIP,
                    url=url,
                )
            )

    return requests


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
                    f"{directories.population_reference_tables}/{CENSUS_RESIDENT_TOTALS_FILENAME}"
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
                destination_relative_path=f"{directories.metro_membership_tables}/{METRO_MEMBERSHIP_FILENAME}",
                file_format=RawFileFormat.EXCEL_XLS,
                url="https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2020/delineation-files/list1_2020.xls",
            )
        )

    for year in sorted(years & HISTORICAL_STUDY_TOTALS_FILENAMES.keys()):
        source_filename = HISTORICAL_STUDY_TOTALS_SOURCE_FILENAMES[year]
        local_filename = HISTORICAL_STUDY_TOTALS_FILENAMES[year]

        requests.append(
            PublicFileRequest(
                destination_relative_path=(
                    f"{directories.population_reference_tables}/{local_filename}"
                ),
                file_format=RawFileFormat.EXCEL_XLSX,
                url=f"https://www2.census.gov/library/working-papers/2002/demo/pop-twps0056/{source_filename}",
            )
        )

    if 1980 in years:
        requests.append(
            PublicFileRequest(
                destination_relative_path=(
                    f"{directories.population_reference_tables}/{RACE_TOTALS_1980_FILENAME}"
                ),
                file_format=RawFileFormat.EXCEL_XLSX,
                url=(
                    "https://www2.census.gov/library/working-papers/2002/demo/pop-twps0056/"
                    f"{RACE_TOTALS_1980_SOURCE_FILENAME}"
                ),
            )
        )

    return requests
