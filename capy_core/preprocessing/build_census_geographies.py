"""Attach population tables to Census boundaries and write one geography file per state."""

import argparse
import re
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd

from capy_core.geography_ids import PART_WIDTHS, normalize_census_part
from capy_core.pipeline_config import build_geography_requests, load_config
from capy_core.preprocessing.population_tables import load_population_table

TARGET_CRS = "esri:102003"  # USA Contiguous Albers Equal Area Conic; meters

PART_COLUMNS = {
    "state": ["STATEFP", "STATEFP20", "STATEFP10", "STATEFP00"],
    "county": ["COUNTYFP", "COUNTYFP20", "COUNTYFP10", "COUNTYFP00"],
    "tract": ["TRACTCE", "TRACTCE20", "TRACTCE10", "TRACTCE00"],
    "block_group": ["BLKGRPCE", "BLKGRPCE20", "BLKGRPCE10", "BLKGRPCE00"],
    "block": ["BLOCKCE", "BLOCKCE20", "BLOCKCE10", "BLOCKCE00"],
    "place": ["PLACEFP"],
}

GEOGRAPHY_PARTS = {
    "counties": ("state", "county"),
    "tracts": ("state", "county", "tract"),
    "block_groups": ("state", "county", "tract", "block_group"),
    "blocks": ("state", "county", "tract", "block"),
    "places": ("state", "place"),
}


@dataclass(frozen=True, slots=True)
class PopulationJoin:
    """Carry matched Census geographies and row counts from a population join.

    The join does not print or write files. Callers use these counts to report
    losses separately from states excluded by the population table's coverage.

    Attributes:
        populated_geography_gdf (gpd.GeoDataFrame): Selected boundaries with matching
            WHITE, BLACK, TOTPOP, and POC counts.
        selected_count (int): Input rows in states represented by the population table.
        unmatched_count (int): Selected rows without a population record.
        excluded_state_count (int): Input rows outside those selected states.
    """

    populated_geography_gdf: gpd.GeoDataFrame
    selected_count: int
    unmatched_count: int
    excluded_state_count: int


def iter_census_geographies(
    year: int, geographies_dir: Path, level_label: str
) -> Iterator[gpd.GeoDataFrame]:
    """Read and project one TIGER shapefile at a time.

    Args:
        year (int): Census year: 2000, 2010, or 2020.
        geographies_dir (Path): Raw boundary directory containing census_{year}_{level_label}.
        level_label (str): Canonical geography level in GEOGRAPHY_PARTS.

    Yields:
        gpd.GeoDataFrame: A standardized shapefile in TARGET_CRS, in sorted path order.
            County files may contain multiple states; other files normally contain one.

    Raises:
        FileNotFoundError: If the year/level directory contains no shapefiles.
        ValueError: If a shapefile lacks usable identifier components.
    """
    shape_dir = geographies_dir / f"census_{year}_{level_label}"
    paths = sorted(path for path in shape_dir.glob("*.shp") if path.is_file())
    if not paths:
        raise FileNotFoundError(
            f"No Census {level_label} shapefiles found in {shape_dir}"
        )
    for path in paths:
        geography_gdf = gpd.read_file(path)
        geography_gdf = standardize_census_geography(geography_gdf, level_label)
        yield geography_gdf.to_crs(TARGET_CRS)


def standardize_census_geography(
    geography_gdf: gpd.GeoDataFrame, level_label: str
) -> gpd.GeoDataFrame:
    """Copy TIGER boundaries and add the identifiers used for population joins.

    JOIN_KEY concatenates the fixed-width FIPS components for the level. GEOID equals
    JOIN_KEY, and GISJOIN prepends G. COUNTYFP is standardized only when county is
    part of the key. TIGER tract codes retain their fixed-width interpretation.

    Args:
        geography_gdf (gpd.GeoDataFrame): Boundaries with identifier columns listed in
            PART_COLUMNS; geometry, CRS, row order, and existing attributes are retained.
        level_label (str): Canonical geography level in GEOGRAPHY_PARTS.

    Returns:
        gpd.GeoDataFrame: A copy with JOIN_KEY, STATEFP, GEOID, GISJOIN, and COUNTYFP
            for county-based levels. The source dataframe is not modified.

    Raises:
        ValueError: If a required identifier column or value is missing.
    """
    geography_gdf = geography_gdf.copy()
    part_names = GEOGRAPHY_PARTS[level_label]
    parts = [geography_part(geography_gdf, part) for part in part_names]
    join_key = parts[0]
    for part in parts[1:]:
        join_key = join_key + part

    geography_gdf["JOIN_KEY"] = join_key
    geography_gdf["STATEFP"] = parts[0]
    if "county" in part_names:
        geography_gdf["COUNTYFP"] = parts[1]
    geography_gdf["GEOID"] = geography_gdf["JOIN_KEY"]
    geography_gdf["GISJOIN"] = "G" + geography_gdf["JOIN_KEY"]
    return geography_gdf


def first_existing_column(
    geography_gdf: gpd.GeoDataFrame, candidates: list[str]
) -> str:
    """Select the first available source column in priority order.

    Args:
        geography_gdf (gpd.GeoDataFrame): Source boundary columns to inspect.
        candidates (list[str]): Candidate names, ordered from preferred to fallback.

    Returns:
        str: First candidate present in the dataframe.

    Raises:
        ValueError: If none of the candidate columns exists.
    """
    for col in candidates:
        if col in geography_gdf.columns:
            return col
    raise ValueError(f"None of these columns were found: {', '.join(candidates)}")


def geography_part(geography_gdf: gpd.GeoDataFrame, part: str) -> pd.Series:
    """Read one TIGER identifier component and pad it to its fixed width.

    TIGER tract fields are padded on the left, including for 2000. The short-code
    conversion used for 2000 Census API population tables does not apply here.

    Args:
        geography_gdf (gpd.GeoDataFrame): Boundaries with a source column for the component.
        part (str): Identifier component listed in PART_COLUMNS and PART_WIDTHS.

    Returns:
        pd.Series: Zero-padded strings with the source index; does not modify the dataframe.

    Raises:
        ValueError: If the source column is absent or any identifier is missing or blank.
    """
    col = first_existing_column(geography_gdf, PART_COLUMNS[part])
    identifiers = geography_gdf[col]
    if identifiers.isna().any() or identifiers.astype(str).str.strip().eq("").any():
        raise ValueError(f"Missing Census {part} identifiers")

    return identifiers.astype(str).str.zfill(PART_WIDTHS[part])


def load_nhgis_geography(
    year: int, geographies_dir: Path, level_label: str
) -> gpd.GeoDataFrame:
    """Load the newest usable NHGIS boundary extract for a year and level.

    Searches only ipums_geography_extracts/{year}/{level_label} beneath geographies_dir.
    Archives are tried newest first; those without a matching shapefile are skipped.
    Retains the historical GISJOIN key and derives state/county codes from NHGIS fields.

    Args:
        year (int): Census year: 1980 or 1990.
        geographies_dir (Path): Raw boundary directory containing ipums_geography_extracts.
        level_label (str): Requested tracts, block_groups, blocks, or counties.

    Returns:
        gpd.GeoDataFrame: Boundaries in their source CRS with JOIN_KEY, GEOID, STATEFP,
            COUNTYFP, and GISJOIN. Projection is the caller's responsibility.

    Raises:
        FileNotFoundError: If the year/level directory contains no extract archives.
        ValueError: If no archive contains a matching shapefile or identifiers are missing.
    """
    extract_dir = geographies_dir / "ipums_geography_extracts" / str(year) / level_label
    paths = sorted(
        extract_dir.glob("*_shape.zip"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not paths:
        raise FileNotFoundError(f"No NHGIS shapefile extracts found in {extract_dir}")

    for path in paths:
        geography_gdf = read_nested_nhgis_shapefile(path, year, level_label)
        if geography_gdf is None:
            continue

        try:
            state, county = state_county_series(geography_gdf)
        except ValueError as exc:
            raise ValueError(
                f"{path} is missing state/county identifier columns."
            ) from exc

        geography_gdf["JOIN_KEY"] = geography_gdf["GISJOIN"].astype("string")
        geography_gdf["GEOID"] = geography_gdf["GISJOIN"].astype("string").str[1:]
        geography_gdf["STATEFP"] = normalize_census_part(state, "state", year)
        geography_gdf["COUNTYFP"] = normalize_census_part(county, "county", year)
        return geography_gdf

    raise ValueError(
        f"No {level_label} NHGIS shapefile found in "
        f"{extract_dir}. "
        "Rerun download_geographies.py for this year and level after updating "
        "the NHGIS selection."
    )


def read_nested_nhgis_shapefile(
    outer_zip: Path, year: int, level_label: str
) -> gpd.GeoDataFrame | None:
    """Read matching shapefiles from an NHGIS archive before removing temporary files.

    Matching files are concatenated by filename. GISJOIN2 is used when GISJOIN is absent;
    rows whose identifier contains nodata are excluded. No reprojection is performed.

    Args:
        outer_zip (Path): NHGIS archive containing shapefiles or nested ZIP archives.
        year (int): Census year used to select shapefile names.
        level_label (str): Geography level used by the NHGIS selection predicates.

    Returns:
        gpd.GeoDataFrame | None: Matching boundaries in the first shapefile's CRS, or None
            when no shapefile matches. Geometries are loaded before temporary extraction ends.

    Raises:
        ValueError: If a selected shapefile has neither GISJOIN nor GISJOIN2.
    """
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

        geography_gdfs = []
        for path in sorted(matches, key=lambda item: item.name.lower()):
            geography_gdf = gpd.read_file(path)
            if "GISJOIN" not in geography_gdf.columns:
                if "GISJOIN2" not in geography_gdf.columns:
                    raise ValueError(f"{path} does not contain a GISJOIN column.")
                # NOTE: We use the nullable string dtype here to avoid making bogus identifiers
                # like "Gnan" when GISJOIN2 is null.
                geography_gdf["GISJOIN"] = "G" + geography_gdf["GISJOIN2"].astype(
                    "string"
                )
            geography_gdfs.append(geography_gdf)

        geography_gdf = gpd.GeoDataFrame(
            pd.concat(geography_gdfs, ignore_index=True), crs=geography_gdfs[0].crs
        )
        geography_gdf = geography_gdf[
            ~geography_gdf["GISJOIN"].astype(str).str.contains("nodata", case=False)
        ].copy()
        return geography_gdf


def nested_shapefile_paths(outer_zip: Path, tmp_dir: Path) -> list[Path]:
    shp_paths = []
    with zipfile.ZipFile(outer_zip) as outer:
        nested_zips = [
            name for name in outer.namelist() if name.lower().endswith(".zip")
        ]
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


def clean_filename(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def is_conflated_nhgis_path(path: Path) -> bool:
    """Return True if the NHGIS path is a conflated or TL-2008 variant.

    Tracts, block groups, and blocks use original boundaries. County selection
    permits these variants because older county extracts may provide no alternative.

    Args:
        path (Path): Shapefile path whose name and parent directory are inspected.

    Returns:
        bool: Whether either name identifies a conflated or TL-2008 variant.
    """
    text = clean_filename(f"{path.parent.name} {path.name}")
    return "conflated" in text or "tl2008" in text


def is_county_sidecar_nhgis_path(path: Path) -> bool:
    """Return True if the shapefile is a county sidecar bundled with a tract file.

    NHGIS sometimes includes a companion county shapefile alongside tract
    shapefiles (e.g. tract_county_...). These should not be treated as
    standalone county or tract geographies.
    """
    text = clean_filename(path.stem)
    compact = text.replace(" ", "")
    return (
        "tractcounty" in compact
        or "countytract" in compact
        or "tract county" in text
        or "county tract" in text
    )


def is_original_tract_family_shapefile(path: Path, year: str) -> bool:
    """Return True if path is a primary NHGIS tract or BNA shapefile for year.

    Excludes conflated variants, county sidecars, and files that don't
    contain the year string in their name.
    """
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
    """Return True if the shapefile stem matches common NHGIS block-group naming patterns."""
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
    """Return True if path is the correct NHGIS shapefile for year and level_label.

    Applies level-specific rules: tracts accept original non-sidecar files;
    counties accept conflated variants (often the only form available for older
    years); block groups and blocks use name-pattern matching while excluding
    sidecars and conflated files.
    """
    if path.suffix.lower() != ".shp" or str(year) not in path.name.lower():
        return False

    if level_label == "tracts":
        return is_original_tract_family_shapefile(path, year)

    if is_county_sidecar_nhgis_path(path):
        return False

    text = clean_filename(path.stem)
    compact = text.replace(" ", "")
    if level_label == "counties":
        # County shapefiles may only exist in conflated form for older years
        # (e.g. 1980 NHGIS only provides US_county_1980_conflated.shp).
        # The original-boundary requirement applies to the smaller units.
        return "county" in text and "tract" not in text

    if is_conflated_nhgis_path(path):
        return False

    if level_label == "block_groups":
        return is_block_group_name(path)
    if level_label == "blocks":
        return ("block" in text or "tabblock" in compact) and not is_block_group_name(
            path
        )
    return False


def first_existing_series(
    geography_gdf: gpd.GeoDataFrame, candidates: list[str]
) -> pd.Series | None:
    """Read the first available historical identifier column as nullable strings.

    Args:
        geography_gdf (gpd.GeoDataFrame): NHGIS boundaries to inspect.
        candidates (list[str]): Source column names in priority order.

    Returns:
        pd.Series | None: Identifier values retaining the source index and nulls,
            or None when none of the candidates exists.
    """
    for col in candidates:
        if col in geography_gdf.columns:
            return geography_gdf[col].astype("string")
    return None


def state_county_series(geography_gdf: gpd.GeoDataFrame) -> tuple[pd.Series, pd.Series]:
    """Extract historical state/county identifiers from NHGIS boundary columns.

    Args:
        geography_gdf (gpd.GeoDataFrame): Boundaries with separate NHGIS state/county
            fields or a combined FIPSSTCO field.

    Returns:
        tuple[pd.Series, pd.Series]: State and county strings padded to two and three
            characters. Separate fields take precedence; nulls remain available for validation.

    Raises:
        ValueError: If neither supported identifier layout is available.
    """
    state = first_existing_series(geography_gdf, ["NHGISST", "STATE80", "STATEA"])
    county = first_existing_series(geography_gdf, ["NHGISCTY", "COUNTY80", "COUNTYA"])
    if state is not None and county is not None:
        return state.str[:2].str.zfill(2), county.str[:3].str.zfill(3)

    fips = first_existing_series(geography_gdf, ["FIPSSTCO"])
    if fips is not None:
        fips = fips.str.zfill(5)
        return fips.str[:2], fips.str[2:5]

    raise ValueError("Missing state/county identifier columns.")


def join_population(
    geography_gdf: gpd.GeoDataFrame, population_df: pd.DataFrame, year: int, level: str
) -> PopulationJoin:
    """Attach population counts to selected boundaries by a one-to-one JOIN_KEY match.

    States absent from the population table are excluded first. Selected rows without
    a population match are checked against the loss policy and then dropped. Geometry,
    CRS, and boundary attributes are retained; the input dataframes are not modified.

    Args:
        geography_gdf (gpd.GeoDataFrame): Boundaries with JOIN_KEY and STATEFP.
        population_df (pd.DataFrame): Normalized population rows with JOIN_KEY, STATEFP,
            WHITE, BLACK, TOTPOP, and POC.
        year (int): Census year used by the join-loss policy.
        level (str): Canonical geography level used by the join-loss policy.

    Returns:
        PopulationJoin: Matched boundaries with int64 counts and the numbers of selected,
            unmatched, and state-excluded input rows. Does not print or write files.

    Raises:
        ValueError: If required columns or values are missing, keys/state codes are blank,
            or unmatched rows exceed the permitted loss rate.
        pd.errors.MergeError: If selected boundaries or population rows have duplicate keys.
    """
    population_columns = ["WHITE", "BLACK", "TOTPOP", "POC"]
    for df, columns in (
        (geography_gdf, ["JOIN_KEY", "STATEFP"]),
        (population_df, ["JOIN_KEY", "STATEFP"] + population_columns),
    ):
        missing_columns = [column for column in columns if column not in df.columns]
        if missing_columns:
            raise ValueError(f"{year} {level}: missing join columns {missing_columns}")
        if df[columns].isna().any().any():
            raise ValueError(
                f"{year} {level}: missing join keys, state codes, or population counts"
            )
        for column in ("JOIN_KEY", "STATEFP"):
            if df[column].astype(str).str.strip().eq("").any():
                raise ValueError(f"{year} {level}: blank {column} values")

    selected_geography_gdf = geography_gdf[
        geography_gdf["STATEFP"].isin(population_df["STATEFP"])
    ].copy()
    joined_geography_gdf = selected_geography_gdf.merge(
        population_df[["JOIN_KEY"] + population_columns],
        on="JOIN_KEY",
        how="left",
        validate="one_to_one",
    )
    unmatched_geography_gdf = joined_geography_gdf[
        joined_geography_gdf["TOTPOP"].isna()
    ]
    validate_population_join(
        year, level, selected_geography_gdf, unmatched_geography_gdf
    )

    populated_geography_gdf = joined_geography_gdf[
        joined_geography_gdf["TOTPOP"].notna()
    ].copy()
    populated_geography_gdf[population_columns] = populated_geography_gdf[
        population_columns
    ].astype("int64")
    return PopulationJoin(
        populated_geography_gdf,
        len(selected_geography_gdf),
        len(unmatched_geography_gdf),
        len(geography_gdf) - len(selected_geography_gdf),
    )


def validate_population_join(
    year: int,
    level: str,
    selected_geography_gdf: gpd.GeoDataFrame,
    unmatched_geography_gdf: gpd.GeoDataFrame,
) -> None:
    """Reject loss above 30% of selected rows, except for 1990 blocks.

    The 1990 block workflow permits unmatched units without a ceiling. This exception
    does not establish why individual rows failed to match. Callers report all losses,
    including those permitted by the exception. An empty selection passes validation.

    Args:
        year (int): Census year of the join.
        level (str): Canonical geography level; blocks has the 1990 exemption.
        selected_geography_gdf (gpd.GeoDataFrame): Boundary rows in population-covered states.
        unmatched_geography_gdf (gpd.GeoDataFrame): Selected rows lacking a population match.

    Raises:
        ValueError: If more than 30% of selected rows are unmatched outside the exemption.
    """
    if year == 1990 and level == "blocks":
        return
    if (
        len(selected_geography_gdf)
        and len(unmatched_geography_gdf) / len(selected_geography_gdf) > 0.3
    ):
        raise ValueError(
            f"{year}: {len(unmatched_geography_gdf)} of {len(selected_geography_gdf)} {level} geometries "
            "did not match population rows (more than 30%)"
        )


def write_state_geography(
    state_geography_gdf: gpd.GeoDataFrame,
    year: int,
    output_dir: Path,
    level: str,
    state_fips: str,
) -> Path:
    """Write one state's population-attributed Census units to a GeoPackage.

    Creates the level directory if necessary. The caller supplies one state's rows;
    this function does not filter by state or reproject the geometries.

    Args:
        state_geography_gdf (gpd.GeoDataFrame): Joined Census units for one state and year.
        year (int): Census year used in the output filename.
        output_dir (Path): Base directory for processed Census geographies.
        level (str): Geography level used in the directory and filename.
        state_fips (str): State FIPS code used in the filename.

    Returns:
        Path: Written output_dir/level/{year}_{level}_{state_fips}.gpkg path.
    """
    output_dir_by_level = output_dir / level
    output_dir_by_level.mkdir(parents=True, exist_ok=True)
    output_path = output_dir_by_level / f"{year}_{level}_{state_fips}.gpkg"
    state_geography_gdf.to_file(output_path, driver="GPKG")
    return output_path


def check_source_inputs(
    year: int, level: str, population_dir: Path, geographies_dir: Path
) -> None:
    """Check population and boundary file presence before geography construction.

    Checks names and file presence, not file contents or completeness of a shapefile's
    sidecar files. NHGIS uses year/level ZIP directories; Census uses shapefile directories.

    Args:
        year (int): Census year to prepare.
        level (str): Canonical geography level to prepare.
        population_dir (Path): Directory containing downloaded population CSVs.
        geographies_dir (Path): Directory containing downloaded boundary extracts.

    Raises:
        FileNotFoundError: If either input is absent. The error lists missing paths and
            corresponding downloader commands.
    """
    provider = "nhgis" if year in (1980, 1990) else "census"
    population_path = population_dir / f"{provider}_{year}_{level}.csv"
    if provider == "nhgis":
        boundary_dir = geographies_dir / "ipums_geography_extracts" / str(year) / level
        boundary_pattern = "*_shape.zip"
    else:
        boundary_dir = geographies_dir / f"census_{year}_{level}"
        boundary_pattern = "*.shp"

    missing = []
    if not population_path.is_file():
        missing.append(
            f"Missing {population_path}. Run poetry run python -m "
            f"capy_core.download.download_population_tables --level {level} --year {year} "
            f'--output-dir "{population_dir}"'
        )
    if not any(path.is_file() for path in boundary_dir.glob(boundary_pattern)):
        missing.append(
            f"Missing boundaries in {boundary_dir}. Run poetry run python -m "
            f"capy_core.download.download_geographies --level {level} --year {year} "
            f'--output-dir "{geographies_dir}" '
            f'--work-dir "{geographies_dir / "ipums_geography_extracts"}"'
        )
    if missing:
        raise FileNotFoundError("\n".join(missing))


def main(config: Path | None = None) -> None:
    """Build node and study-area definition geographies selected by a YAML config.

    Checks source presence for every request before writing. Population is loaded once
    per year/level; boundaries are joined and written by state beneath the resolved
    census_geographies_path. Prints join losses and missing-state summaries by level.

    Args:
        config (Path | None, optional): Pipeline YAML path. None selects config.yaml in
            the capy_core directory, independently of the working directory. Defaults to None.

    Raises:
        FileNotFoundError: If configuration or required source files are absent.
        ValueError: If configuration, source data, or population joins are invalid.
    """
    config_path = (
        config
        if config is not None
        else Path(__file__).resolve().parents[1] / "config.yaml"
    )
    resolved_config = load_config(config_path)
    requests = build_geography_requests(resolved_config)
    for request in requests:
        check_source_inputs(
            request.year,
            request.geography,
            resolved_config.raw_population_path,
            resolved_config.raw_geographies_path,
        )

    states_by_level: dict[str, dict[int, set[str]]] = {}
    for request in requests:
        year, level = request.year, request.geography
        print(f"Creating {year} {level} geography geopackage files", flush=True)
        population_df = load_population_table(
            year, resolved_config.raw_population_path, level
        )
        if year in (1980, 1990):
            geography_gdf = load_nhgis_geography(
                year, resolved_config.raw_geographies_path, level
            )
            state_geographies = (
                state_geography_gdf
                for _, state_geography_gdf in geography_gdf.to_crs(TARGET_CRS).groupby(
                    "STATEFP"
                )
            )
        else:
            # County TIGER files are national; other levels normally contain one state per file.
            state_geographies = (
                state_geography_gdf
                for geography_gdf in iter_census_geographies(
                    year, resolved_config.raw_geographies_path, level
                )
                for _, state_geography_gdf in geography_gdf.groupby("STATEFP")
            )

        states_written: set[str] = set()
        for state_geography_gdf in state_geographies:
            state_fips = state_geography_gdf["STATEFP"].iloc[0]
            population_join = join_population(
                state_geography_gdf, population_df, year, level
            )
            print(
                f"  FIPS {state_fips}: {population_join.selected_count:,} selected, "
                f"{population_join.unmatched_count:,} unmatched, "
                f"{population_join.excluded_state_count:,} excluded by state",
                flush=True,
            )
            if population_join.populated_geography_gdf.empty:
                continue

            write_state_geography(
                population_join.populated_geography_gdf,
                year,
                resolved_config.census_geographies_path,
                level,
                state_fips,
            )
            states_written.add(state_fips)

        states_by_level.setdefault(level, {})[year] = states_written
        print(
            f"  {len(states_written)} {level} geopackages written for {year}",
            flush=True,
        )

    for level, states_by_year in states_by_level.items():
        report_missing_states(states_by_year, level)


def report_missing_states(states_by_year: dict[int, set[str]], level: str) -> None:
    """Print states missing from some requested years of one geography level.

    Args:
        states_by_year (dict[int, set[str]]): Successfully written state FIPS codes per year.
        level (str): Geography level named in the messages.

    Only states present in at least one year are reported. The function does not inspect
    files or modify the supplied mapping.
    """
    all_states: set[str] = set().union(*states_by_year.values())
    for state_fips in sorted(all_states):
        missing_years = [
            year
            for year, states in sorted(states_by_year.items())
            if state_fips not in states
        ]
        if missing_years:
            print(
                f"  Note: FIPS {state_fips} has no {level} geopackage for {missing_years} "
                "(no matched source data for those years)",
                flush=True,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build node and study-area definition geographies selected by a YAML config.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Pipeline YAML configuration (defaults to capy_core/config.yaml).",
    )
    args = parser.parse_args()
    main(**vars(args))
