import re
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional

import geopandas as gpd
import pandas as pd
import typer


YEARS = [1980, 1990, 2000, 2010, 2020]
POPULATION_DIR = Path("data/raw/population")
GEOGRAPHIES_DIR = Path("data/raw/geographies")
OUTPUT_DIR = Path("data/processed/census_geographies")

PART_WIDTHS = {
    "state": 2,
    "county": 3,
    "tract": 6,
    "block_group": 1,
    "block": 4,
}

PART_COLUMNS = {
    "state": ["STATEFP", "STATEFP20", "STATEFP10", "STATEFP00"],
    "county": ["COUNTYFP", "COUNTYFP20", "COUNTYFP10", "COUNTYFP00"],
    "tract": ["TRACTCE", "TRACTCE20", "TRACTCE10", "TRACTCE00"],
    "block_group": ["BLKGRPCE", "BLKGRPCE20", "BLKGRPCE10", "BLKGRPCE00"],
    "block": ["BLOCKCE", "BLOCKCE20", "BLOCKCE10", "BLOCKCE00"],
}

POPULATION_PART_COLUMNS = {
    "state": "state",
    "county": "county",
    "tract": "tract",
    "block_group": "block group",
    "block": "block",
}

LEVELS = {
    "county": {"label": "counties", "parts": ("state", "county"), "width": 5},
    "counties": {"label": "counties", "parts": ("state", "county"), "width": 5},
    "tract": {
        "label": "tracts",
        "parts": ("state", "county", "tract"),
        "width": 11,
    },
    "tracts": {
        "label": "tracts",
        "parts": ("state", "county", "tract"),
        "width": 11,
    },
    "block_group": {
        "label": "block_groups",
        "parts": ("state", "county", "tract", "block_group"),
        "width": 12,
    },
    "block_groups": {
        "label": "block_groups",
        "parts": ("state", "county", "tract", "block_group"),
        "width": 12,
    },
    "block": {
        "label": "blocks",
        "parts": ("state", "county", "tract", "block"),
        "width": 15,
    },
    "blocks": {
        "label": "blocks",
        "parts": ("state", "county", "tract", "block"),
        "width": 15,
    },
}


def clean_filename(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def is_conflated_nhgis_path(path: Path) -> bool:
    text = clean_filename(f"{path.parent.name} {path.name}")
    return "conflated" in text or "tl2008" in text


def is_county_sidecar_nhgis_path(path: Path) -> bool:
    text = clean_filename(path.stem)
    compact = text.replace(" ", "")
    return (
        "tractcounty" in compact
        or "countytract" in compact
        or "tract county" in text
        or "county tract" in text
    )


def is_original_tract_family_shapefile(path: Path, year: str) -> bool:
    if path.suffix.lower() != ".shp":
        return False

    name = path.name.lower()
    if (
        str(year) not in name
        or is_conflated_nhgis_path(path)
        or is_county_sidecar_nhgis_path(path)
    ):
        return False

    text = clean_filename(path.stem)
    return "tract" in text or "bna" in text


def is_block_group_name(path: Path) -> bool:
    text = clean_filename(path.stem)
    compact = text.replace(" ", "")
    return (
        "blockgroup" in compact
        or "blckgrp" in compact
        or "blkgrp" in compact
        or ("block" in text and "group" in text)
        or re.search(r"(^| )bg( |$)", text) is not None
    )


def is_nhgis_shapefile_for_level(path: Path, year: str, level_label: str) -> bool:
    if path.suffix.lower() != ".shp" or str(year) not in path.name.lower():
        return False

    if level_label == "tracts":
        return is_original_tract_family_shapefile(path, year)

    if is_conflated_nhgis_path(path) or is_county_sidecar_nhgis_path(path):
        return False

    text = clean_filename(path.stem)
    compact = text.replace(" ", "")
    if level_label == "counties":
        return "county" in text and "tract" not in text
    if level_label == "block_groups":
        return is_block_group_name(path)
    if level_label == "blocks":
        return ("block" in text or "tabblock" in compact) and not is_block_group_name(path)
    return False


def to_int(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).astype("int64")


def normalize_part(series: pd.Series, part: str, year: int) -> pd.Series:
    text = series.astype(str).str.strip()
    width = PART_WIDTHS[part]
    if part == "tract" and year == 2000:
        short = text.str.len() < width
        normalized = text.str.zfill(width)
        normalized.loc[short] = text.loc[short].str.zfill(4).str.ljust(width, "0")
        return normalized
    return text.str.zfill(width)


def require_columns(df: pd.DataFrame, columns: List[str], path: Path) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{path} is missing columns: {', '.join(missing)}")


def validate_level(level: str) -> str:
    if level not in LEVELS:
        supported = ", ".join(sorted(LEVELS))
        raise ValueError(
            f"Unsupported census geography level {level!r}; "
            f"supported values are: {supported}."
        )
    return LEVELS[level]["label"]


def parse_years(years: Optional[str], year_values: Optional[List[int]]) -> List[int]:
    if year_values:
        return year_values
    if years:
        return [int(year) for year in years.replace(",", " ").split()]
    return YEARS


def indexed_prefixes(df: pd.DataFrame, base: str) -> List[str]:
    pattern = re.compile(rf"^{base}[A-Z]*001$")
    return sorted({col[:-3] for col in df.columns if pattern.fullmatch(col)})


def sum_indexed_columns(
    df: pd.DataFrame,
    prefixes: List[str],
    indexes: range,
) -> pd.Series:
    total = pd.Series(0, index=df.index, dtype="int64")
    for prefix in prefixes:
        for index in indexes:
            col = f"{prefix}{index:03d}"
            if col in df.columns:
                total = total + to_int(df[col])
    return total


def read_nhgis_1980_population(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    race_prefixes = indexed_prefixes(df, "C9D")
    hispanic_race_prefixes = indexed_prefixes(df, "C9G")
    if not race_prefixes:
        raise ValueError(f"{path} is missing 1980 race population columns.")

    require_columns(df, ["GISJOIN", "STATEA", "COUNTYA"], path)
    white = sum_indexed_columns(df, race_prefixes, range(1, 2)) - sum_indexed_columns(
        df, hispanic_race_prefixes, range(1, 2)
    )
    black = sum_indexed_columns(df, race_prefixes, range(2, 3)) - sum_indexed_columns(
        df, hispanic_race_prefixes, range(2, 3)
    )
    return pd.DataFrame(
        {
            "JOIN_KEY": df["GISJOIN"],
            "GISJOIN": df["GISJOIN"],
            "STATEFP": df["STATEA"].str.zfill(2),
            "COUNTYFP": df["COUNTYA"].str.zfill(3),
            "WHITE": white,
            "BLACK": black,
            "TOTPOP": sum_indexed_columns(df, race_prefixes, range(1, 16)),
        }
    )


def read_nhgis_1990_population(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    race_cols = [f"ET2{i:03d}" for i in range(1, 11)]
    require_columns(df, ["GISJOIN", "STATEA", "COUNTYA"] + race_cols, path)
    gisjoin = df["GISJOIN"].astype(str)
    return pd.DataFrame(
        {
            "JOIN_KEY": gisjoin,
            "GISJOIN": gisjoin,
            "STATEFP": df["STATEA"].str.zfill(2),
            "COUNTYFP": df["COUNTYA"].str.zfill(3),
            "WHITE": to_int(df["ET2001"]),
            "BLACK": to_int(df["ET2002"]),
            "TOTPOP": sum(to_int(df[col]) for col in race_cols),
        }
    )


def read_census_population(
    df: pd.DataFrame,
    path: Path,
    year: int,
    level_label: str,
) -> pd.DataFrame:
    config = LEVELS[level_label]
    part_columns = [POPULATION_PART_COLUMNS[part] for part in config["parts"]]
    require_columns(
        df,
        part_columns + ["TOTPOP", "NH_WHITE", "NH_BLACK"],
        path,
    )

    parts = [
        normalize_part(df[POPULATION_PART_COLUMNS[part]], part, year)
        for part in config["parts"]
    ]
    join_key = parts[0]
    for part in parts[1:]:
        join_key = join_key + part

    pop = pd.DataFrame(
        {
            "JOIN_KEY": join_key,
            "GISJOIN": "G" + join_key,
            "STATEFP": parts[0],
            "COUNTYFP": parts[1] if len(parts) > 1 else "",
            "WHITE": to_int(df["NH_WHITE"]),
            "BLACK": to_int(df["NH_BLACK"]),
            "TOTPOP": to_int(df["TOTPOP"]),
        }
    )
    return pop


def read_population(
    year: int,
    population_dir: Path,
    level_label: str,
) -> pd.DataFrame:
    if year in (1980, 1990):
        path = population_dir / f"nhgis_{year}_{level_label}.csv"
    else:
        path = population_dir / f"census_{year}_{level_label}.csv"

    df = pd.read_csv(path, dtype=str, encoding_errors="replace")
    if "YEAR" in df.columns:
        df = df[df["YEAR"].astype(str).str.fullmatch(r"\d{4}", na=False)].copy()

    if year == 1980:
        pop = read_nhgis_1980_population(df, path)
    elif year == 1990:
        pop = read_nhgis_1990_population(df, path)
    else:
        pop = read_census_population(df, path, year, level_label)

    pop["POC"] = pop["TOTPOP"] - pop["WHITE"]
    return pop


def first_existing_column(gdf: gpd.GeoDataFrame, candidates: List[str]) -> str:
    for col in candidates:
        if col in gdf.columns:
            return col
    raise ValueError(f"None of these columns were found: {', '.join(candidates)}")


def geography_part(gdf: gpd.GeoDataFrame, part: str) -> pd.Series:
    col = first_existing_column(gdf, PART_COLUMNS[part])
    return gdf[col].astype(str).str.zfill(PART_WIDTHS[part])


def standardize_census_geography(
    gdf: gpd.GeoDataFrame,
    level_label: str,
) -> gpd.GeoDataFrame:
    config = LEVELS[level_label]
    parts = [geography_part(gdf, part) for part in config["parts"]]
    join_key = parts[0]
    for part in parts[1:]:
        join_key = join_key + part

    gdf["JOIN_KEY"] = join_key
    gdf["STATEFP"] = parts[0]
    gdf["COUNTYFP"] = parts[1] if len(parts) > 1 else ""
    gdf["GEOID"] = gdf["JOIN_KEY"]
    gdf["GISJOIN"] = "G" + gdf["JOIN_KEY"]
    return gdf


def read_census_geography(
    year: int,
    geographies_dir: Path,
    level_label: str,
) -> gpd.GeoDataFrame:
    shape_dir = geographies_dir / f"census_{year}_{level_label}"
    paths = sorted(path for path in shape_dir.glob("*.shp") if path.is_file())
    if not paths:
        raise FileNotFoundError(f"No Census {level_label} shapefiles found in {shape_dir}")

    frames = [gpd.read_file(path) for path in paths]
    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    return standardize_census_geography(gdf, level_label)


def nested_shapefile_paths(outer_zip: Path, tmp_dir: Path) -> List[Path]:
    shp_paths = []
    with zipfile.ZipFile(outer_zip) as outer:
        nested_zips = [name for name in outer.namelist() if name.lower().endswith(".zip")]
        if not nested_zips:
            shape_dir = tmp_dir / outer_zip.stem
            outer.extractall(shape_dir)
            return list(shape_dir.rglob("*.shp"))

        for name in nested_zips:
            nested_path = tmp_dir / Path(name).name
            nested_path.write_bytes(outer.read(name))

            shape_dir = tmp_dir / nested_path.stem
            with zipfile.ZipFile(nested_path) as nested:
                nested.extractall(shape_dir)

            shp_paths.extend(shape_dir.rglob("*.shp"))
    return shp_paths


def read_nested_nhgis_shapefile(
    outer_zip: Path,
    year: int,
    level_label: str,
) -> Optional[gpd.GeoDataFrame]:
    year_label = str(year)
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp_dir = Path(tmp_name)
        shp_paths = nested_shapefile_paths(outer_zip, tmp_dir)
        matches = [
            path
            for path in shp_paths
            if is_nhgis_shapefile_for_level(path, year_label, level_label)
        ]
        if not matches:
            return None

        frames = []
        for path in sorted(matches, key=lambda item: item.name.lower()):
            gdf = gpd.read_file(path)
            if "GISJOIN" not in gdf.columns:
                if "GISJOIN2" not in gdf.columns:
                    raise ValueError(f"{path} does not contain a GISJOIN column.")
                gdf["GISJOIN"] = "G" + gdf["GISJOIN2"].astype(str)
            frames.append(gdf)

        gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
        gdf = gdf[
            ~gdf["GISJOIN"].astype(str).str.contains("nodata", case=False)
        ].copy()
        return gdf


def first_existing_series(
    gdf: gpd.GeoDataFrame,
    candidates: List[str],
) -> Optional[pd.Series]:
    for col in candidates:
        if col in gdf.columns:
            return gdf[col].astype("string")
    return None


def state_county_series(gdf: gpd.GeoDataFrame) -> tuple[pd.Series, pd.Series]:
    state = first_existing_series(gdf, ["NHGISST", "STATE80", "STATEA"])
    county = first_existing_series(gdf, ["NHGISCTY", "COUNTY80", "COUNTYA"])
    if state is not None and county is not None:
        return state.str[:2].str.zfill(2), county.str[:3].str.zfill(3)

    fips = first_existing_series(gdf, ["FIPSSTCO"])
    if fips is not None:
        fips = fips.str.zfill(5)
        return fips.str[:2], fips.str[2:5]

    raise ValueError("Missing state/county identifier columns.")


def nhgis_extract_dirs(
    geographies_dir: Path,
    year: int,
    level_label: str,
) -> List[Path]:
    base_dir = geographies_dir / "ipums_geography_extracts" / str(year)
    dirs = [base_dir / level_label]
    if base_dir not in dirs:
        dirs.append(base_dir)
    return dirs


def read_nhgis_geography(
    year: int,
    geographies_dir: Path,
    level_label: str,
) -> gpd.GeoDataFrame:
    extract_dirs = nhgis_extract_dirs(geographies_dir, year, level_label)
    paths = []
    for extract_dir in extract_dirs:
        paths.extend(extract_dir.glob("*_shape.zip"))
    paths = sorted(set(paths), key=lambda path: path.stat().st_mtime, reverse=True)
    if not paths:
        dirs = ", ".join(str(path) for path in extract_dirs)
        raise FileNotFoundError(f"No NHGIS shapefile extracts found in: {dirs}")

    for path in paths:
        gdf = read_nested_nhgis_shapefile(path, year, level_label)
        if gdf is None:
            continue

        try:
            state, county = state_county_series(gdf)
        except ValueError as exc:
            raise ValueError(f"{path} is missing state/county identifier columns.") from exc

        gdf["JOIN_KEY"] = gdf["GISJOIN"].astype(str)
        gdf["GEOID"] = gdf["GISJOIN"].astype(str).str[1:]
        gdf["STATEFP"] = state
        gdf["COUNTYFP"] = county
        return gdf

    raise ValueError(
        f"No {level_label} NHGIS shapefile found in "
        f"{', '.join(str(path) for path in extract_dirs)}. "
        "Rerun download_geographies.py for this year and level after updating "
        "the NHGIS selection."
    )


TARGET_CRS = "esri:102003"  # USA Contiguous Albers Equal Area Conic; meters


def read_geography(
    year: int,
    geographies_dir: Path,
    level_label: str,
) -> gpd.GeoDataFrame:
    if year in (1980, 1990):
        gdf = read_nhgis_geography(year, geographies_dir, level_label)
    else:
        gdf = read_census_geography(year, geographies_dir, level_label)
    return gdf.to_crs(TARGET_CRS)


def join_population(
    gdf: gpd.GeoDataFrame,
    pop: pd.DataFrame,
    year: int,
    level_label: str,
) -> gpd.GeoDataFrame:
    state_fips = set(pop["STATEFP"])
    gdf = gdf[gdf["STATEFP"].isin(state_fips)].copy()

    merged = gdf.merge(
        pop[["JOIN_KEY", "WHITE", "BLACK", "TOTPOP", "POC"]],
        on="JOIN_KEY",
        how="left",
        validate="one_to_one",
    )

    missing = merged["TOTPOP"].isna().sum()
    if missing:
        # Blocks include many water-only and unpopulated geographic areas that have
        # no row in the population CSV; a high miss rate is expected and not an error.
        threshold = 0.50 if level_label == "blocks" else 0.01
        if missing / len(merged) > threshold:
            raise ValueError(
                f"{year}: {missing} {level_label} geometries did not match "
                "population rows."
            )
        merged = merged[merged["TOTPOP"].notna()].copy()

    for col in ["WHITE", "BLACK", "TOTPOP", "POC"]:
        merged[col] = merged[col].astype("int64")

    return merged


def write_processed(
    gdf: gpd.GeoDataFrame,
    year: int,
    output_dir: Path,
    level_label: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{year}_{level_label}.gpkg"
    gdf.to_file(output_path, driver="GPKG")
    return output_path


def main(
    level: str = typer.Option(
        "tracts",
        help="tracts, block_groups, blocks, or counties",
    ),
    years: Optional[str] = typer.Option(None, "--years", help="Space- or comma-separated years."),
    year_values: Optional[List[int]] = typer.Option(None, "--year", "-y"),
    population_dir: Path = typer.Option(POPULATION_DIR),
    geographies_dir: Path = typer.Option(GEOGRAPHIES_DIR),
    output_dir: Path = typer.Option(OUTPUT_DIR),
) -> None:
    level_label = validate_level(level)
    run_years = parse_years(years, year_values)

    for year in run_years:
        if year == 1980 and level_label in ("block_groups", "blocks"):
            print(
                f"Skipping 1980 {level_label}: NHGIS does not publish 1980 "
                "block group or block boundary shapefiles.",
                flush=True,
            )
            continue
        print(f"Processing {year} {level_label}")
        pop = read_population(year, population_dir, level_label)
        gdf = read_geography(year, geographies_dir, level_label)
        merged = join_population(gdf, pop, year, level_label)
        path = write_processed(merged, year, output_dir, level_label)
        print(path)


if __name__ == "__main__":
    typer.run(main)
