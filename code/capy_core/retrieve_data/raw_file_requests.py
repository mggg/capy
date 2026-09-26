"""Describe the raw inputs: Census tables, NHGIS extracts, and published files."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, ClassVar, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator

from capy_core.geography_types import GeographyLevel

from .nhgis.identifiers import NhgisDataset, NhgisGeographyLevel


class RawFileFormat(StrEnum):
    """Expected contents of a raw file, used to choose its basic validation checks.

    These labels describe source files; they do not request conversion to another format.
    ZIP_ARCHIVE includes population archives, while SHAPEFILE_ZIP identifies boundary archives.
    """

    CENSUS_TABLE_JSON = "census"
    ZIP_ARCHIVE = "zip"
    SHAPEFILE_ZIP = "shapes"
    EXCEL_XLS = "xls"
    EXCEL_XLSX = "xlsx"
    CSV = "csv"
    DBASE_TABLE = "dbf"


def validate_relative_file_path(value: str) -> str:
    """Require a relative file path without dot components, backslashes, or control characters."""
    path = PurePosixPath(value)
    if (
        not value
        or value == "."
        or path.is_absolute()
        or str(path) != value
        or "\\" in value
        or any(ord(character) < 32 for character in value)
        or ".." in path.parts
    ):
        raise ValueError("Use a relative file path without dot components or control characters")

    return value


RelativeFilePath = Annotated[str, AfterValidator(validate_relative_file_path)]


@dataclass(frozen=True, kw_only=True)
class RawFileDestination:
    """A destination shared by the concrete raw-input records.

    Attributes:
        destination_relative_path (str): File location beneath raw_data_directory. Must be
            relative, without dot components or control characters.
    """

    destination_relative_path: str

    def __post_init__(self) -> None:
        """Check the destination when an input is constructed."""
        validate_relative_file_path(self.destination_relative_path)


CensusYear = Literal[1980, 1990, 2000, 2010, 2020]


@dataclass(frozen=True)
class GeographyRequest:
    """One year and kind of geographic unit needed by the run.

    Both population tables and boundary files use this selection. It can describe units to
    analyze, such as 1990 tracts, or units needed to define a study area, such as 2020 counties.

    Attributes:
        census_year (CensusYear): One of 1980, 1990, 2000, 2010, or 2020.
        geography_level (GeographyLevel): Kind of unit whose population and boundaries are needed.
    """

    census_year: CensusYear
    geography_level: GeographyLevel


class CensusDataset(StrEnum):
    """Census table products, with the codes used in Census API addresses.

    PL_94_171 selects redistricting data. SUMMARY_FILE_1 supplies the 2000 block-group population
    tables used by this pipeline.
    """

    PL_94_171 = "pl"
    SUMMARY_FILE_1 = "sf1"


@dataclass(frozen=True, kw_only=True)
class CensusFileRequest(RawFileDestination):
    """A statewide Census PL/SF1 table, or a national table of state totals.

    Attributes:
        census_year (int): 2000, 2010, or 2020.
        dataset (CensusDataset): PL_94_171 for redistricting data, or SUMMARY_FILE_1.
        variables (str): Comma-separated Census variable names, including NAME if desired.
        geography_level (GeographyLevel): Kind of unit to request; STATE selects national totals.
        state_code (str | None): Two-digit FIPS code. Omit only for national state totals.
    """

    census_year: Literal[2000, 2010, 2020]
    dataset: CensusDataset
    variables: str
    geography_level: GeographyLevel
    state_code: str | None = None
    # ClassVar fixes the format for this input kind; it is not a constructor argument.
    file_format: ClassVar[RawFileFormat] = RawFileFormat.CENSUS_TABLE_JSON

    def __post_init__(self) -> None:
        """Require supported years and a state code for substate tables."""
        super().__post_init__()
        if self.census_year not in (2000, 2010, 2020) or not isinstance(
            self.dataset, CensusDataset
        ):
            raise ValueError("Use a supported Census year and dataset")
        if not self.variables or not isinstance(self.geography_level, GeographyLevel):
            raise ValueError("Specify Census variables and a supported geographic level")
        if self.geography_level == GeographyLevel.STATE:
            if self.state_code is not None:
                raise ValueError("National state totals do not take a state code")
        elif (
            self.state_code is None or len(self.state_code) != 2 or not self.state_code.isdecimal()
        ):
            raise ValueError("Substate Census tables require a two-digit state code")


@dataclass(frozen=True, kw_only=True)
class PublicFileRequest(RawFileDestination):
    """A published file downloaded without query parameters.

    Attributes:
        url (str): HTTPS download URL without credentials, query parameters, or a fragment.
        file_format (RawFileFormat): ZIP_ARCHIVE, SHAPEFILE_ZIP, EXCEL_XLS, EXCEL_XLSX, CSV, or DBASE_TABLE.
            Selects the basic file check without converting the file.
    """

    url: str
    file_format: RawFileFormat

    def __post_init__(self) -> None:
        """Check the destination, supported public-file format, and download URL."""
        super().__post_init__()
        if (
            not isinstance(self.file_format, RawFileFormat)
            or self.file_format == RawFileFormat.CENSUS_TABLE_JSON
        ):
            raise ValueError("Public files require an archive, Excel, or CSV format")

        url = urlsplit(self.url)
        if url.scheme != "https" or not url.hostname or url.username or url.query or url.fragment:
            raise ValueError(
                "Downloads require an HTTPS URL without credentials or query parameters"
            )


@dataclass(frozen=True, kw_only=True)
class NhgisTableFileRequest(RawFileDestination):
    """An NHGIS table extract, downloaded as a ZIP of CSV files with headers.

    Attributes:
        dataset_name (NhgisDataset): NHGIS dataset identifier, such as 1980_STF1.
        tables (tuple[str, ...]): One or more table identifiers within that dataset.
        geographic_levels (tuple[NhgisGeographyLevel, ...]): NHGIS level codes, such as county or tract.
        breakdowns (tuple[str, ...]): Area breakdown codes; empty uses the dataset default.
        description (str): Optional label displayed in the NHGIS account.
    """

    dataset_name: NhgisDataset
    tables: tuple[str, ...]
    geographic_levels: tuple[NhgisGeographyLevel, ...]
    breakdowns: tuple[str, ...] = ()
    description: str = ""
    file_format: ClassVar[RawFileFormat] = RawFileFormat.ZIP_ARCHIVE

    def __post_init__(self) -> None:
        """Require a dataset and at least one table and geographic level."""
        super().__post_init__()
        if not self.dataset_name or not self.tables or not self.geographic_levels:
            raise ValueError("NHGIS tables require a dataset, tables, and geographic levels")


@dataclass(frozen=True, kw_only=True)
class NhgisBoundaryFileRequest(RawFileDestination):
    """An NHGIS boundary extract, downloaded as a shapefile ZIP.

    Attributes:
        shapefiles (tuple[str, ...]): One or more NHGIS shapefile identifiers, including vintage.
    """

    shapefiles: tuple[str, ...]
    file_format: ClassVar[RawFileFormat] = RawFileFormat.SHAPEFILE_ZIP

    def __post_init__(self) -> None:
        """Require at least one boundary product."""
        super().__post_init__()
        if not self.shapefiles:
            raise ValueError("NHGIS boundaries require at least one shapefile")


RawFileRequest = (
    CensusFileRequest | PublicFileRequest | NhgisTableFileRequest | NhgisBoundaryFileRequest
)
