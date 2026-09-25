"""Check that retrieved files are nonempty and have the expected basic structure."""

import json
import math
import zipfile
from pathlib import Path
from typing import Any

from .raw_file_requests import RawFileFormat


def check_raw_file(path: Path, file_format: RawFileFormat) -> None:
    """Check that a raw file exists, contains data, and passes the checks for its format.

    ZIP files, shapefile archives, and XLSX workbooks must have a readable archive listing with at
    least one file. Their individual contents are not read here. Census JSON tables must have a
    header and rows with the same number of values. Other formats are checked only for a nonempty
    file. These checks do not establish that populations, geographic codes, or coverage are
    correct; those checks belong to later processing stages. No checksum is compared here.

    Args:
        path (Path): Downloaded or existing raw file.
        file_format (RawFileFormat): Expected source format from the input definition.

    Raises:
        ValueError: The path is not a file, the file is empty, an archive has no files or uses an
            unsupported ZIP version, or a Census table has invalid JSON or the wrong structure.
        zipfile.BadZipFile: The file listing of a ZIP-based format cannot be read.
        OSError: The file cannot be read.
    """
    if file_format == RawFileFormat.CENSUS_TABLE_JSON:
        load_census_table(path)
        return

    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Raw input must be a nonempty file")

    if file_format in (
        RawFileFormat.ZIP_ARCHIVE,
        RawFileFormat.SHAPEFILE_ZIP,
        RawFileFormat.EXCEL_XLSX,
    ):
        try:
            with zipfile.ZipFile(path) as archive:
                if not any(not member.is_dir() for member in archive.infolist()):
                    raise ValueError("Archive contains no files")
        except NotImplementedError:
            raise ValueError("Archive requires an unsupported ZIP version") from None


def load_census_table(path: Path) -> list[list[Any]]:
    """Read a saved Census response and require the same number of values in every row.

    The first row supplies the column headers, and at least one data row must follow it. Values
    are returned unchanged: this does not check column names, geographic codes, population values,
    or whether all expected areas are present. Nonfinite numbers such as NaN and Infinity are
    rejected, including numbers that overflow Python's floating-point range.

    Args:
        path (Path): Saved Census response containing a header and at least one data row.

    Returns:
        list[list[Any]]: Parsed table, including its header as the first row.

    Raises:
        ValueError: The path is not a file, is empty, contains invalid JSON, or lacks the required
            header and consistently sized rows.
        OSError: The file cannot be read.
    """
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Raw input must be a nonempty file")

    table = json.loads(
        path.read_bytes(),
        parse_float=parse_finite_json_number,
        parse_constant=parse_finite_json_number,
    )
    if not isinstance(table, list) or len(table) < 2:
        raise ValueError("Census response must contain a header and data rows")

    header = table[0]
    if not isinstance(header, list) or not header:
        raise ValueError("Census response has no column header")
    if any(not isinstance(row, list) or len(row) != len(header) for row in table[1:]):
        raise ValueError("Census response has inconsistent row widths")

    return table


def parse_finite_json_number(value: str) -> float:
    """Parse a JSON number, raising ValueError for NaN, infinity, or floating-point overflow."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Census response contains a nonfinite number")

    return number
