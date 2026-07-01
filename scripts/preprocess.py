import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional

import geopandas as gpd
import pandas as pd
import typer


YEARS = [1980, 1990, 2000, 2010, 2020]
POPULATION_DIR = Path("census_raw/population")
GEOGRAPHIES_DIR = Path("census_raw/geographies")
OUTPUT_DIR = Path("processed")


def to_int(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0).astype("int64")


def census_2000_tract_code(value: str) -> str:
    value = str(value).strip()
    if len(value) <= 4:
        return value.zfill(4) + "00"
    return value.zfill(6)


def require_columns(df: pd.DataFrame, columns: List[str], path: Path) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{path} is missing columns: {', '.join(missing)}")


def read_population(year: int, population_dir: Path) -> pd.DataFrame:
    if year in (1980, 1990):
        path = population_dir / f"nhgis_{year}_tracts.csv"
    else:
        path = population_dir / f"census_{year}_tracts.csv"

    df = pd.read_csv(path, dtype=str, encoding_errors="replace")
    df = df[df["YEAR"].astype(str).str.fullmatch(r"\d{4}", na=False)].copy()

    if year == 1980:
        race_cols = [f"C9D{i:03d}" for i in range(1, 16)]
        hispanic_race_cols = [f"C9G{i:03d}" for i in range(1, 5)]
        require_columns(
            df,
            ["GISJOIN", "STATEA", "COUNTYA"] + race_cols + hispanic_race_cols,
            path,
        )
        pop = pd.DataFrame(
            {
                "JOIN_KEY": df["GISJOIN"],
                "GISJOIN": df["GISJOIN"],
                "STATEFP": df["STATEA"].str.zfill(2),
                "COUNTYFP": df["COUNTYA"].str.zfill(3),
                "WHITE": to_int(df["C9D001"]) - to_int(df["C9G001"]),
                "BLACK": to_int(df["C9D002"]) - to_int(df["C9G002"]),
                "TOTPOP": sum(to_int(df[col]) for col in race_cols),
            }
        )
    elif year == 1990:
        race_cols = [f"ET2{i:03d}" for i in range(1, 11)]
        require_columns(
            df,
            ["GISJOIN", "STATEA", "COUNTYA"] + race_cols,
            path,
        )
        pop = pd.DataFrame(
            {
                "JOIN_KEY": df["GISJOIN"],
                "GISJOIN": df["GISJOIN"],
                "STATEFP": df["STATEA"].str.zfill(2),
                "COUNTYFP": df["COUNTYA"].str.zfill(3),
                "WHITE": to_int(df["ET2001"]),
                "BLACK": to_int(df["ET2002"]),
                "TOTPOP": sum(to_int(df[col]) for col in race_cols),
            }
        )
    else:
        require_columns(df, ["GEOID", "state", "county", "TOTPOP", "NH_WHITE", "NH_BLACK"], path)
        state = df["state"].str.zfill(2)
        county = df["county"].str.zfill(3)
        if year == 2000:
            tract = df["tract"].apply(census_2000_tract_code)
        else:
            tract = df["tract"].str.zfill(6)
        join_key = state + county + tract

        pop = pd.DataFrame(
            {
                "JOIN_KEY": join_key,
                "GISJOIN": "G" + join_key,
                "STATEFP": state,
                "COUNTYFP": county,
                "WHITE": to_int(df["NH_WHITE"]),
                "BLACK": to_int(df["NH_BLACK"]),
                "TOTPOP": to_int(df["TOTPOP"]),
            }
        )

    pop["POC"] = pop["TOTPOP"] - pop["WHITE"]
    return pop


def standardize_census_geography(year: int, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if year == 2000:
        gdf["JOIN_KEY"] = gdf["CTIDFP00"].astype(str).str.zfill(11)
        gdf["STATEFP"] = gdf["STATEFP00"].astype(str).str.zfill(2)
        gdf["COUNTYFP"] = gdf["COUNTYFP00"].astype(str).str.zfill(3)
    elif year == 2010:
        gdf["JOIN_KEY"] = gdf["GEOID10"].astype(str).str.zfill(11)
        gdf["STATEFP"] = gdf["STATEFP10"].astype(str).str.zfill(2)
        gdf["COUNTYFP"] = gdf["COUNTYFP10"].astype(str).str.zfill(3)
    elif year == 2020:
        gdf["JOIN_KEY"] = gdf["GEOID"].astype(str).str.zfill(11)
        gdf["STATEFP"] = gdf["STATEFP"].astype(str).str.zfill(2)
        gdf["COUNTYFP"] = gdf["COUNTYFP"].astype(str).str.zfill(3)
    else:
        raise ValueError(f"{year} is not a Census TIGER geography year.")

    gdf["GEOID"] = gdf["JOIN_KEY"]
    gdf["GISJOIN"] = "G" + gdf["JOIN_KEY"]
    return gdf


def read_census_geography(year: int, geographies_dir: Path) -> gpd.GeoDataFrame:
    shape_dir = geographies_dir / f"census_{year}_tracts"
    paths = sorted(path for path in shape_dir.glob("*.shp") if path.is_file())
    if not paths:
        raise FileNotFoundError(f"No Census tract shapefiles found in {shape_dir}")

    frames = [gpd.read_file(path) for path in paths]
    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    return standardize_census_geography(year, gdf)


def read_nested_nhgis_shapefile(outer_zip: Path) -> Optional[gpd.GeoDataFrame]:
    year = outer_zip.parent.name
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp_dir = Path(tmp_name)
        shp_paths = []
        with zipfile.ZipFile(outer_zip) as outer:
            nested_zips = [
                name
                for name in outer.namelist()
                if name.lower().endswith(".zip")
            ]
            for name in nested_zips:
                nested_path = tmp_dir / Path(name).name
                nested_path.write_bytes(outer.read(name))

                shape_dir = tmp_dir / nested_path.stem
                with zipfile.ZipFile(nested_path) as nested:
                    nested.extractall(shape_dir)

                shp_paths.extend(shape_dir.glob("*.shp"))

        target_names = [f"us_tract_{year}.shp", f"us_bna_{year}.shp"]
        matches = [
            path
            for target_name in target_names
            for path in shp_paths
            if path.name.lower() == target_name
        ]
        if not matches:
            return None

        frames = []
        for path in matches:
            gdf = gpd.read_file(path)
            if "GISJOIN" not in gdf.columns:
                raise ValueError(f"{path} does not contain a GISJOIN column.")
            frames.append(gdf)

        gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
        gdf = gdf[
            ~gdf["GISJOIN"].astype(str).str.contains("nodata", case=False)
        ].copy()
        return gdf

    return None


def read_nhgis_geography(year: int, geographies_dir: Path) -> gpd.GeoDataFrame:
    extract_dir = geographies_dir / "ipums_geography_extracts" / str(year)
    paths = sorted(extract_dir.glob("*_shape.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not paths:
        raise FileNotFoundError(f"No NHGIS shapefile extracts found in {extract_dir}")

    for path in paths:
        gdf = read_nested_nhgis_shapefile(path)
        if gdf is not None:
            state = gdf["NHGISST"].astype("string").str[:2]
            county = gdf["NHGISCTY"].astype("string").str[:3]
            if "STATE80" in gdf.columns:
                state = state.fillna(gdf["STATE80"].astype("string").str.zfill(2))
            if "COUNTY80" in gdf.columns:
                county = county.fillna(gdf["COUNTY80"].astype("string").str.zfill(3))

            gdf["JOIN_KEY"] = gdf["GISJOIN"].astype(str)
            gdf["GEOID"] = gdf["GISJOIN"].str[1:]
            gdf["STATEFP"] = state
            gdf["COUNTYFP"] = county
            return gdf

    raise ValueError(
        f"No tract-level NHGIS shapefile found in {extract_dir}. "
        "The downloaded extract may be county-level; rerun download_geographies.py "
        "for this year and level after updating the NHGIS selection."
    )


def read_geography(year: int, geographies_dir: Path) -> gpd.GeoDataFrame:
    if year in (1980, 1990):
        return read_nhgis_geography(year, geographies_dir)
    return read_census_geography(year, geographies_dir)


def join_population(gdf: gpd.GeoDataFrame, pop: pd.DataFrame, year: int) -> gpd.GeoDataFrame:
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
        if missing / len(merged) > 0.01:
            raise ValueError(f"{year}: {missing} tract geometries did not match population rows.")
        merged = merged[merged["TOTPOP"].notna()].copy()

    for col in ["WHITE", "BLACK", "TOTPOP", "POC"]:
        merged[col] = merged[col].astype("int64")

    return merged


def write_processed(gdf: gpd.GeoDataFrame, year: int, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{year}_tracts.shp"
    gdf.to_file(output_path)
    return output_path


def main(
    years: Optional[List[int]] = typer.Option(None, "--year", "-y"),
    population_dir: Path = typer.Option(POPULATION_DIR),
    geographies_dir: Path = typer.Option(GEOGRAPHIES_DIR),
    output_dir: Path = typer.Option(OUTPUT_DIR),
) -> None:
    run_years = years or YEARS

    for year in run_years:
        print(f"Processing {year}")
        pop = read_population(year, population_dir)
        gdf = read_geography(year, geographies_dir)
        merged = join_population(gdf, pop, year)
        path = write_processed(merged, year, output_dir)
        print(path)


if __name__ == "__main__":
    typer.run(main)
