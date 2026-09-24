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
        pd.DataFrame: JOIN_KEY, GISJOIN, STATEFP, WHITE, BLACK, TOTPOP, and POC; county-based
            geographies also include COUNTYFP.

    Raises:
        ValueError: If required columns or counts are invalid.
        FileNotFoundError: If the requested population table is absent.
    """
    provider = "nhgis" if year in (1980, 1990) else "census"
    source = population_dir / f"{provider}_{year}_{level}.csv"
    source_population_df = pd.read_csv(source, dtype=str, encoding_errors="replace")
    if "YEAR" in source_population_df.columns:
        # NHGIS CSVs may include a second header row describing each column.
        descriptive_header = source_population_df["YEAR"].eq("Data File Year")
        if provider == "nhgis" and "GISJOIN" in source_population_df:
            descriptive_header &= source_population_df["GISJOIN"].eq("GIS Join Match Code")
            source_population_df = source_population_df.loc[~descriptive_header].copy()
        if not source_population_df["YEAR"].eq(str(year)).all():
            raise ValueError(f"{source} contains population rows outside Census year {year}")

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

    C9D supplies race counts and C9G supplies Hispanic race counts. When the download combines
    tables with different subarea columns, NHGIS_SOURCE_FILE identifies the rows belonging to each
    table. Entirely null layouts introduced by concatenating total-area and urban/rural files are
    omitted per source. Missing cells within a present component are rejected.

    Args:
        source_population_df (pd.DataFrame): NHGIS rows with GISJOIN, STATEA, COUNTYA, C9D/C9G
            columns, and optionally NHGIS_SOURCE_FILE.
        source (Path): Source CSV path used in validation errors; not read here.

    Returns:
        pd.DataFrame: JOIN_KEY, GISJOIN, STATEFP, COUNTYFP, WHITE, BLACK, and TOTPOP, preserving
            input row order and index. WHITE and BLACK exclude Hispanic counts.

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
        for suffixes in (("",), ("AA", "AB")):
            prefixes = {base + suffix for base in ("C9D", "C9G") for suffix in suffixes}
            columns = [
                column for column in source_table_df.columns if column[:-3] in prefixes
            ]
            if columns and source_table_df[columns].isna().all().all():
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
    """Normalize 1980 STF1 race counts for total areas or urban/rural components.

    Unsuffixed columns describe total areas. In the combined component layout, AA means urban and AB
    means rural. Both race tables must cover the same components; combining total-area and component
    counts would count people twice. Each NT7 component has 15 race cells, and each NT9B component
    has four Hispanic race cells.

    Args:
        source_population_df (pd.DataFrame): One source table's rows with GISJOIN, STATEA, COUNTYA,
            and complete C9D/C9G columns for either supported layout.
        source (Path): Source label used in validation errors; not read here.

    Returns:
        pd.DataFrame: JOIN_KEY, GISJOIN, STATEFP, COUNTYFP, WHITE, BLACK, and TOTPOP, preserving the
            source index without modifying the input. WHITE and BLACK exclude Hispanic counts;
            TOTPOP sums all 15 race cells.

    Raises:
        ValueError: If layouts differ, overlap, or are unsupported; if required cells are missing;
            or if counts or identifiers are invalid.
    """
    race_suffixes = {
        prefix[3:] for prefix in indexed_prefixes(source_population_df, "C9D")
    }
    hispanic_suffixes = {
        prefix[3:] for prefix in indexed_prefixes(source_population_df, "C9G")
    }
    if race_suffixes != hispanic_suffixes:
        raise ValueError(
            f"{source}: C9D and C9G must have the same geographic breakdowns"
        )
    if race_suffixes not in ({""}, {"AA", "AB"}):
        raise ValueError(
            f"{source}: expected total-area columns or both urban (AA) and rural (AB) "
            "components, without mixing layouts"
        )
    require_columns(source_population_df, ["GISJOIN", "STATEA", "COUNTYA"], source)

    population_counts_df = pd.DataFrame(
        0,
        index=source_population_df.index,
        columns=["WHITE", "BLACK", "TOTPOP"],
        dtype="int64",
    )
    component_present = pd.Series(False, index=source_population_df.index)
    for suffix in sorted(race_suffixes):
        component_counts_df = parse_nhgis_1980_component(
            source_population_df, suffix, source
        )
        component_present |= source_population_df[f"C9D{suffix}001"].notna()
        population_counts_df += component_counts_df

    if not component_present.all():
        raise ValueError(
            f"{source}: a population row has no reported geographic component"
        )

    population_df = pd.DataFrame(
        {
            "JOIN_KEY": source_population_df["GISJOIN"],
            "GISJOIN": source_population_df["GISJOIN"],
            "STATEFP": normalize_census_part(
                source_population_df["STATEA"], "state", 1980
            ),
            "COUNTYFP": normalize_census_part(
                source_population_df["COUNTYA"], "county", 1980
            ),
        }
    )
    return pd.concat([population_df, population_counts_df], axis=1)


def parse_nhgis_1980_component(
    source_population_df: pd.DataFrame, suffix: str, source: Path
) -> pd.DataFrame:
    """Parse one complete STF1 race/Hispanic component, allowing an absent urban/rural part.

    A component is absent only when all 15 race and four Hispanic race cells are null. In the
    urban/rural layout, that component contributes zero. Partially null components and missing
    total-area counts are errors. Blank values are not generally zero counts.

    Args:
        source_population_df (pd.DataFrame): Population rows in a validated STF1 layout.
        suffix (str): Empty for total area, AA for urban, or AB for rural.
        source (Path): Source label used in validation errors; not read here.

    Returns:
        pd.DataFrame: Non-Hispanic WHITE/BLACK counts and TOTPOP, preserving the input index.

    Raises:
        ValueError: If any component column is missing, counts are invalid, or Hispanic White/Black
            counts exceed their corresponding race counts.
    """
    race_columns = [f"C9D{suffix}{index:03d}" for index in range(1, 16)]
    hispanic_columns = [f"C9G{suffix}{index:03d}" for index in range(1, 5)]
    columns = race_columns + hispanic_columns
    require_columns(source_population_df, columns, source)
    component_counts_df = source_population_df[columns].copy()
    if suffix:
        absent_component = component_counts_df.isna().all(axis=1)
        component_counts_df.loc[absent_component, :] = "0"

    for column in columns:
        component_counts_df[column] = parse_population_counts(
            component_counts_df[column], source=source, column=column
        )

    white = (
        component_counts_df[race_columns[0]] - component_counts_df[hispanic_columns[0]]
    )
    black = (
        component_counts_df[race_columns[1]] - component_counts_df[hispanic_columns[1]]
    )
    return pd.DataFrame(
        {
            "WHITE": parse_population_counts(
                white, source=source, column=f"WHITE ({suffix or 'total'})"
            ),
            "BLACK": parse_population_counts(
                black, source=source, column=f"BLACK ({suffix or 'total'})"
            ),
            "TOTPOP": component_counts_df[race_columns].sum(axis=1),
        }
    )


def indexed_prefixes(source_population_df: pd.DataFrame, base: str) -> list[str]:
    """Find distinct NHGIS column prefixes, including incomplete tables.

    Args:
        source_population_df (pd.DataFrame): Source table whose column names are inspected.
        base (str): NHGIS table code, such as C9D or C9G.

    Returns:
        list[str]: Sorted unique prefixes with zero or more uppercase ASCII letters between the base
            and a three-digit cell number.
    """
    pattern = re.compile(rf"^{base}[A-Z]*[0-9]{{3}}$")
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

    The owning parser checks its required columns first. Absent optional columns contribute zero;
    present columns must contain valid counts.

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

    ET2001 and ET2002 are non-Hispanic White and Black counts. TOTPOP sums ET2001 through ET2010,
    including the Hispanic race categories.

    Args:
        source_population_df (pd.DataFrame): NHGIS rows with GISJOIN, STATEA, COUNTYA, and ET2001
            through ET2010.
        source (Path): Source CSV path used in validation errors; not read here.

    Returns:
        pd.DataFrame: JOIN_KEY (= GISJOIN), GISJOIN, STATEFP, COUNTYFP, WHITE, BLACK, and TOTPOP,
            preserving the source index without modifying the input.

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

    The source FIPS components determine JOIN_KEY; the downloaded GEOID is ignored. Short 2000 tract
    encodings use the Census API normalization rule. NH_WHITE and NH_BLACK become WHITE and BLACK.
    Places have no county component in their key.

    Args:
        source_population_df (pd.DataFrame): Census API rows with level-specific FIPS columns and
            NH_WHITE, NH_BLACK, and TOTPOP counts.
        source (Path): Source CSV path used in validation errors; not read here.
        year (int): Census year: 2000, 2010, or 2020.
        level (str): Canonical geography level in POPULATION_PARTS.

    Returns:
        pd.DataFrame: JOIN_KEY, GISJOIN, STATEFP, WHITE, BLACK, and TOTPOP, plus COUNTYFP for
            county-based levels. Preserves the source index without modifying the input.

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

    Source tables are expected to contain Census integer counts. Values use pandas numeric
    conversion before validation rather than exact decimal-token parsing.

    Args:
        series (pd.Series): Counts from a source column or a derived calculation.
        source (Path): Source CSV path for error messages.
        column (str): Source column or derived count name.

    Returns:
        pd.Series: Integer counts with the original index.

    Raises:
        ValueError: If counts are missing, nonnumeric, fractional, negative, nonfinite, or outside
            the signed int64 range.
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
