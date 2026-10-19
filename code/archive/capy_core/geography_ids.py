"""Normalize Census identifier components shared by source adapters."""

import pandas as pd

PART_WIDTHS = {
    "state": 2,
    "county": 3,
    "tract": 6,
    "block_group": 1,
    "block": 4,
    "place": 5,
}


def normalize_census_part(series: pd.Series, part: str, year: int) -> pd.Series:
    """Normalize a Census key component, retaining the special 2000 tract encoding.

    Args:
        series (pd.Series): Source identifier values, with their original index.
        part (str): Census key component named in PART_WIDTHS.
        year (int): Census year; short 2000 tract codes encode whole tracts.

    Returns:
        pd.Series: Padded identifier strings.

    Raises:
        ValueError: If an identifier is missing or blank.
    """
    if series.isna().any():
        raise ValueError(f"Missing Census {part} identifiers")

    text = series.astype(str).str.strip()
    if text.eq("").any():
        raise ValueError(f"Blank Census {part} identifiers")
    width = PART_WIDTHS[part]
    if part == "tract" and year == 2000:
        short = text.str.len() < width
        normalized = text.str.zfill(width)
        normalized.loc[short] = text.loc[short].str.zfill(4).str.ljust(width, "0")
        return normalized
    return text.str.zfill(width)
