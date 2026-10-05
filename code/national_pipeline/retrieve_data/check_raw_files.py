"""Check that retrieved files are nonempty and have the expected basic structure."""

import zipfile
from pathlib import Path

from .census.read_tables import load_census_table
from .raw_file_requests import RawFileFormat

ARCHIVE_FORMATS = (
    RawFileFormat.ZIP_ARCHIVE,
    RawFileFormat.SHAPEFILE_ZIP,
    RawFileFormat.EXCEL_XLSX,
)


def check_raw_file(path: Path, file_format: RawFileFormat) -> None:
    """Check that a newly downloaded raw file contains data and passes the checks for its format.

    ZIP files, shapefile archives, and XLSX workbooks must have a readable archive listing with at
    least one file. Their individual contents are not read here. Census JSON tables must have a
    header and rows with the same number of values, and must open and close as a JSON array
    within their first and last 64 bytes. Other formats are checked only for a nonempty
    file. These checks do not establish that populations, geographic codes, or coverage are
    correct; those checks belong to later processing stages.
    Files already published by an earlier run get the cheaper check_existing_raw_file().

    Args:
        path (Path): Downloaded raw file, still under its temporary name.
        file_format (RawFileFormat): Expected source format from the input definition.

    Raises:
        ValueError: The path is not a file, the file is empty, an archive has no files or uses an
            unsupported ZIP version, or a Census table has invalid JSON or the wrong structure.
        zipfile.BadZipFile: The file listing of a ZIP-based format cannot be read.
        OSError: The file cannot be read.
    """
    if file_format == RawFileFormat.CENSUS_TABLE_JSON:
        load_census_table(path)
        # Anything published must also pass the cheaper rerun check.
        check_census_table_brackets(path)
        return

    check_nonempty_file(path)
    if file_format in ARCHIVE_FORMATS:
        check_archive_listing(path)


def check_existing_raw_file(path: Path, file_format: RawFileFormat) -> None:
    """Check a file published by an earlier run without reading all of it.

    A published file already passed check_raw_file() before receiving its final name, so this
    only guards against later truncation or replacement. Census tables must be nonempty and begin
    and end with the JSON array brackets; they are not parsed again, so a table that was edited
    into malformed JSON is reported when population processing parses it, and tables no later
    stage reads are not rechecked. Archives must still have a readable listing with at least one
    file. Other formats must be nonempty.

    Args:
        path (Path): Existing raw file at its final name.
        file_format (RawFileFormat): Expected source format from the input definition.

    Raises:
        ValueError: The path is not a file, the file is empty, a Census table is not a complete
            JSON array, or an archive has no files or uses an unsupported ZIP version.
        zipfile.BadZipFile: The file listing of a ZIP-based format cannot be read.
        OSError: The file cannot be read.
    """
    check_nonempty_file(path)
    if file_format == RawFileFormat.CENSUS_TABLE_JSON:
        check_census_table_brackets(path)
    elif file_format in ARCHIVE_FORMATS:
        check_archive_listing(path)


def check_nonempty_file(path: Path) -> None:
    """Require a regular file with at least one byte."""
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Raw input must be a nonempty file")


def check_archive_listing(path: Path) -> None:
    """Require a readable ZIP listing that names at least one file; members are not read."""
    try:
        with zipfile.ZipFile(path) as archive:
            if not any(not member.is_dir() for member in archive.infolist()):
                raise ValueError("Archive contains no files")
    except NotImplementedError:
        raise ValueError("Archive requires an unsupported ZIP version") from None


def check_census_table_brackets(path: Path) -> None:
    """Require a saved Census table to open and close as an array of rows, reading only its ends.

    A Census response is an array of row arrays, so the file starts with "[[" and ends with "]]"
    once whitespace is ignored. A file cut off inside a row, or exactly after a row, fails this.
    """
    with path.open("rb") as stream:
        head = stream.read(64).translate(None, b" \t\r\n")
        stream.seek(max(path.stat().st_size - 64, 0))
        tail = stream.read().translate(None, b" \t\r\n")

    if not head.startswith(b"[[") or not tail.endswith(b"]]"):
        raise ValueError("Census table is not a complete array of rows")
