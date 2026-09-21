"""Read source population tables and normalize their join keys and race counts."""

import re
from pathlib import Path

import pandas as pd

from capy_core.geography_ids import normalize_census_part

POPULATION_PART_COLUMNS = {
    "state": "state",
    "county": "county",
    "tract": "tract",
    "block_group": "block group",
    "block": "block",
    "place": "place",
}
POPULATION_PARTS = {
    "counties": ("state", "county"),
    "tracts": ("state", "county", "tract"),
    "block_groups": ("state", "county", "tract", "block_group"),
    "blocks": ("state", "county", "tract", "block"),
    "places": ("state", "place"),
}


def load_population_table(year: int, population_dir: Path, level: str) -> pd.DataFrame:
    """Load a population CSV and append POC as total population minus non-Hispanic White.

    Args:
        year (int): Census year.
        population_dir (Path): Directory containing downloaded population CSVs.
        level (str): Canonical geography level, such as tracts or counties.

    Returns:
        pd.DataFrame: JOIN_KEY, GISJOIN, STATEFP, WHITE, BLACK, TOTPOP, and POC;
            county-based geographies also include COUNTYFP.

    Raises:
        ValueError: If required columns or counts are invalid.
        FileNotFoundError: If the requested population table is absent.
    """
    provider = "nhgis" if year in (1980, 1990) else "census"
    source = population_dir / f"{provider}_{year}_{level}.csv"
    source_population_df = pd.read_csv(source, dtype=str, encoding_errors="replace")
    if "YEAR" in source_population_df.columns:
        # NHGIS CSVs may include a second header row describing each column.
        source_population_df = source_population_df[
            source_population_df["YEAR"].str.fullmatch(r"\d{4}", na=False)
        ].copy()

    if year == 1980:
        population_df = parse_nhgis_1980_population(source_population_df, source)
    elif year == 1990:
        population_df = parse_nhgis_1990_population(source_population_df, source)
    else:
        population_df = parse_census_population(
            source_population_df, source, year, level
        )

    population_df["POC"] = parse_population_counts(
        population_df["TOTPOP"] - population_df["WHITE"], source=source, column="POC"
    )
    return population_df


def parse_nhgis_1980_population(
    source_population_df: pd.DataFrame, source: Path
) -> pd.DataFrame:
    """Parse 1980 population counts, keeping concatenated source tables separate.

    C9D supplies race counts and C9G supplies Hispanic race counts. When the download
    combines tables with different subarea columns, NHGIS_SOURCE_FILE identifies the
    rows belonging to each table. Entirely null prefixes within a source table are
    omitted before parsing; missing cells within a retained prefix are rejected.

    Args:
        source_population_df (pd.DataFrame): NHGIS rows with GISJOIN, STATEA, COUNTYA,
            C9D/C9G columns, and optionally NHGIS_SOURCE_FILE.
        source (Path): Source CSV path used in validation errors; not read here.

    Returns:
        pd.DataFrame: JOIN_KEY, GISJOIN, STATEFP, COUNTYFP, WHITE, BLACK, and TOTPOP,
            preserving input row order and index. WHITE and BLACK exclude Hispanic counts.

    Raises:
        ValueError: If source-file identifiers, required columns, or counts are invalid.
    """
    if (
        "NHGIS_SOURCE_FILE" not in source_population_df.columns
        or source_population_df.empty
    ):
        return parse_nhgis_1980_table(source_population_df, source)
    if source_population_df["NHGIS_SOURCE_FILE"].isna().any():
        raise ValueError(f"{source} has missing NHGIS_SOURCE_FILE values")

    # Group using row positions; source index labels may repeat.
    indexed_population_df = source_population_df.reset_index(drop=True)
    population_dfs = []
    for source_file, source_table_df in indexed_population_df.groupby(
        "NHGIS_SOURCE_FILE", sort=False
    ):
        absent_columns = []
        for base in ("C9D", "C9G"):
            for prefix in indexed_prefixes(source_table_df, base):
                columns = [
                    column
                    for column in source_table_df.columns
                    if column[:-3] == prefix
                ]
                if source_table_df[columns].isna().all().all():
                    absent_columns.extend(columns)

        source_table_df = source_table_df.drop(columns=absent_columns)
        population_dfs.append(
            parse_nhgis_1980_table(source_table_df, Path(f"{source}:{source_file}"))
        )

    population_df = pd.concat(population_dfs).sort_index()
    population_df.index = source_population_df.index
    return population_df


def parse_nhgis_1980_table(
    source_population_df: pd.DataFrame, source: Path
) -> pd.DataFrame:
    """Normalize race counts from one 1980 NHGIS source table.

    Unsuffixed C9D has all 15 NT7 cells. Split prefixes require White and Black
    cells; other race cells contribute when present in that extract layout.
    Race and Hispanic prefixes are discovered independently. Each Hispanic
    prefix must supply White and Black cells, regardless of its race-table counterpart.
    WHITE and BLACK subtract Hispanic counts from their respective race totals.
    TOTPOP sums all available C9D cells numbered 001 through 015.

    Args:
        source_population_df (pd.DataFrame): One table's rows and applicable C9D/C9G
            columns, with GISJOIN, STATEA, and COUNTYA identifiers.
        source (Path): Source label used in validation errors; not read here.

    Returns:
        pd.DataFrame: JOIN_KEY, GISJOIN, STATEFP, COUNTYFP, WHITE, BLACK, and TOTPOP,
            preserving the source index without modifying the input.

    Raises:
        ValueError: If required identifiers or counts are missing or invalid, or
            Hispanic subtraction produces a negative count.
    """
    race_prefixes = indexed_prefixes(source_population_df, "C9D")
    if not race_prefixes:
        raise ValueError(f"{source} is missing 1980 race population columns")
    hispanic_prefixes = indexed_prefixes(source_population_df, "C9G")
    if not hispanic_prefixes:
        raise ValueError(
            f"{source} is missing 1980 Hispanic race population columns "
            "(C9G001 or subarea variants)"
        )
    required = ["GISJOIN", "STATEA", "COUNTYA"]
    for prefix in race_prefixes:
        indexes = range(1, 16) if prefix == "C9D" else range(1, 3)
        required.extend(f"{prefix}{index:03d}" for index in indexes)
    required.extend(
        f"{prefix}{index:03d}" for prefix in hispanic_prefixes for index in (1, 2)
    )
    require_columns(source_population_df, required, source)

    white = sum_indexed_columns(
        source_population_df, race_prefixes, range(1, 2), source
    )
    white -= sum_indexed_columns(
        source_population_df, hispanic_prefixes, range(1, 2), source
    )
    black = sum_indexed_columns(
        source_population_df, race_prefixes, range(2, 3), source
    )
    black -= sum_indexed_columns(
        source_population_df, hispanic_prefixes, range(2, 3), source
    )

    return pd.DataFrame(
        {
            "JOIN_KEY": source_population_df["GISJOIN"],
            "GISJOIN": source_population_df["GISJOIN"],
            "STATEFP": normalize_census_part(
                source_population_df["STATEA"], "state", 1980
            ),
            "COUNTYFP": normalize_census_part(
                source_population_df["COUNTYA"], "county", 1980
            ),
            "WHITE": parse_population_counts(white, source=source, column="WHITE"),
            "BLACK": parse_population_counts(black, source=source, column="BLACK"),
            "TOTPOP": sum_indexed_columns(
                source_population_df, race_prefixes, range(1, 16), source
            ),
        }
    )


def indexed_prefixes(source_population_df: pd.DataFrame, base: str) -> list[str]:
    """Find distinct NHGIS column prefixes containing cell 001.

    Args:
        source_population_df (pd.DataFrame): Source table whose column names are inspected.
        base (str): NHGIS table code, such as C9D or C9G.

    Returns:
        list[str]: Sorted unique prefixes with zero or more uppercase ASCII letters
            between the base and the 001 cell suffix.
    """
    pattern = re.compile(rf"^{base}[A-Z]*001$")
    return sorted(
        {
            column[:-3]
            for column in source_population_df.columns
            if pattern.fullmatch(column)
        }
    )


def sum_indexed_columns(
    source_population_df: pd.DataFrame,
    prefixes: list[str],
    indexes: range,
    source: Path,
) -> pd.Series:
    """Sum the requested population cells for each row.

    The owning parser checks its required columns first. Absent optional columns
    contribute zero; present columns must contain valid counts.

    Args:
        source_population_df (pd.DataFrame): Source population columns to sum.
        prefixes (list[str]): NHGIS table/subarea prefixes, such as C9D or C9DAA.
        indexes (range): Cell numbers appended to each prefix as three digits.
        source (Path): Source label used in validation errors; not read here.

    Returns:
        pd.Series: Row totals as int64, preserving the source index.

    Raises:
        ValueError: If a present cell contains a missing or invalid population count.
    """
    total = pd.Series(0, index=source_population_df.index, dtype="int64")
    for prefix in prefixes:
        for index in indexes:
            column = f"{prefix}{index:03d}"
            if column not in source_population_df.columns:
                continue

            counts = parse_population_counts(
                source_population_df[column], source=source, column=column
            )

            total += counts

    return total


def parse_nhgis_1990_population(
    source_population_df: pd.DataFrame, source: Path
) -> pd.DataFrame:
    """Normalize 1990 NP10 population counts and NHGIS join identifiers.

    ET2001 and ET2002 are non-Hispanic White and Black counts. TOTPOP sums
    ET2001 through ET2010, including the Hispanic race categories.

    Args:
        source_population_df (pd.DataFrame): NHGIS rows with GISJOIN, STATEA, COUNTYA,
            and ET2001 through ET2010.
        source (Path): Source CSV path used in validation errors; not read here.

    Returns:
        pd.DataFrame: JOIN_KEY (= GISJOIN), GISJOIN, STATEFP, COUNTYFP, WHITE, BLACK,
            and TOTPOP, preserving the source index without modifying the input.

    Raises:
        ValueError: If required columns, state/county identifiers, or counts are invalid.
    """
    race_columns = [f"ET2{index:03d}" for index in range(1, 11)]
    require_columns(
        source_population_df, ["GISJOIN", "STATEA", "COUNTYA"] + race_columns, source
    )
    return pd.DataFrame(
        {
            "JOIN_KEY": source_population_df["GISJOIN"],
            "GISJOIN": source_population_df["GISJOIN"],
            "STATEFP": normalize_census_part(
                source_population_df["STATEA"], "state", 1990
            ),
            "COUNTYFP": normalize_census_part(
                source_population_df["COUNTYA"], "county", 1990
            ),
            "WHITE": parse_population_counts(
                source_population_df["ET2001"], source=source, column="ET2001"
            ),
            "BLACK": parse_population_counts(
                source_population_df["ET2002"], source=source, column="ET2002"
            ),
            "TOTPOP": sum_indexed_columns(
                source_population_df, ["ET2"], range(1, 11), source
            ),
        }
    )


def parse_census_population(
    source_population_df: pd.DataFrame, source: Path, year: int, level: str
) -> pd.DataFrame:
    """Normalize Census API population columns and construct join identifiers.

    The source FIPS components determine JOIN_KEY; the downloaded GEOID is ignored.
    Short 2000 tract encodings use the Census API normalization rule. NH_WHITE and
    NH_BLACK become WHITE and BLACK. Places have no county component in their key.

    Args:
        source_population_df (pd.DataFrame): Census API rows with level-specific FIPS
            columns and NH_WHITE, NH_BLACK, and TOTPOP counts.
        source (Path): Source CSV path used in validation errors; not read here.
        year (int): Census year: 2000, 2010, or 2020.
        level (str): Canonical geography level in POPULATION_PARTS.

    Returns:
        pd.DataFrame: JOIN_KEY, GISJOIN, STATEFP, WHITE, BLACK, and TOTPOP, plus COUNTYFP
            for county-based levels. Preserves the source index without modifying the input.

    Raises:
        ValueError: If required columns, identifier components, or counts are invalid.
    """
    part_names = POPULATION_PARTS[level]
    part_columns = [POPULATION_PART_COLUMNS[part] for part in part_names]
    require_columns(
        source_population_df, part_columns + ["TOTPOP", "NH_WHITE", "NH_BLACK"], source
    )
    parts = [
        normalize_census_part(
            source_population_df[POPULATION_PART_COLUMNS[part]], part, year
        )
        for part in part_names
    ]
    join_key = parts[0]
    for part in parts[1:]:
        join_key = join_key + part

    population_df = pd.DataFrame(
        {"JOIN_KEY": join_key, "GISJOIN": "G" + join_key, "STATEFP": parts[0]}
    )
    if "county" in part_names:
        population_df["COUNTYFP"] = parts[1]
    for source_column, column in (
        ("NH_WHITE", "WHITE"),
        ("NH_BLACK", "BLACK"),
        ("TOTPOP", "TOTPOP"),
    ):
        population_df[column] = parse_population_counts(
            source_population_df[source_column], source=source, column=source_column
        )

    return population_df


def require_columns(df: pd.DataFrame, columns: list[str], source: Path) -> None:
    """Check that a source table contains each required column.

    Args:
        df (pd.DataFrame): Table to inspect without modifying it.
        columns (list[str]): Required column names.
        source (Path): Source label to include in an error.

    Raises:
        ValueError: If any required column is absent; lists all missing columns.
    """
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{source} is missing columns: {', '.join(missing)}")


def parse_population_counts(
    series: pd.Series, *, source: Path, column: str
) -> pd.Series:
    """Validate nonnegative integer counts before converting to signed int64.

    Source tables are expected to contain Census integer counts. Values use pandas
    numeric conversion before validation, rather than exact decimal-token parsing.

    Args:
        series (pd.Series): Counts from a source column or a derived calculation.
        source (Path): Source CSV path for error messages.
        column (str): Source column or derived count name.

    Returns:
        pd.Series: Integer counts with the original index.

    Raises:
        ValueError: If counts are missing, nonnumeric, fractional, negative, nonfinite,
            or outside the signed int64 range.
    """
    try:
        counts = pd.to_numeric(series, errors="raise")
    except (ValueError, TypeError) as error:
        raise ValueError(
            f"{source}: {column} contains nonnumeric population counts"
        ) from error

    valid = counts.notna() & (counts >= 0) & (counts < 2**63) & (counts % 1 == 0)
    if not valid.all():
        raise ValueError(
            f"{source}: {column} must contain nonnegative int64 population counts"
        )

    return counts.astype("int64")
