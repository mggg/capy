"""Read saved Census API tables and validate their JSON structure."""

import json
import math
from pathlib import Path
from typing import Any


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
