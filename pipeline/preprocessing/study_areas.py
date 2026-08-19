"""
The script builds study area definition files (.gpkg + .json), one per study area. It writes two files per study area into "data/processed/study_area_definitions":
{type}_{code}_{vintage}.gpkg with the boundary geometry
{type}_{code}_{vintage}.json with metadata (CBSA code, title, component counties, total population)
The .gpkg files are what overlaps.py reads as study_area_glob.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.utils.definitions import StudyArea

import tqdm
import pandas as pd
import typer
import geopandas as gpd
import json
from pathlib import Path


def main(filename: str = "data/raw/study_area_sources/list1_march_2020.xls", definition_geographies: str = None, output_dir: str = "data/processed/study_area_definitions", study_area_type: str = "cbsa", definition_vintage: str = "march_2020", cbsa_geographies: str = None):
    if study_area_type == "counties":
        study_area_type = "county"
    if study_area_type not in {"cbsa", "max_county", "county", "max_city"}:
        raise ValueError(f"Unsupported study area type {study_area_type}. Use 'cbsa', 'max_county', 'max_city', or 'county'.")

    if definition_geographies is None:
        if study_area_type == "max_city":
            definition_geographies = "data/processed/census_geographies/places/2020_places_*.gpkg"
        else:
            definition_geographies = "data/processed/census_geographies/counties/2020_counties_*.gpkg"
    if cbsa_geographies is None and study_area_type == "max_city":
        cbsa_geographies = "data/processed/census_geographies/counties/2020_counties_*.gpkg"

    if study_area_type == "county":
        build_county_definitions(definition_geographies, output_dir, definition_vintage or Path(definition_geographies).stem.split("_", 1)[0])
        return

    if study_area_type == "max_county":
        build_max_county_definitions(filename, definition_geographies, output_dir, definition_vintage or Path(definition_geographies).stem.split("_", 1)[0])
        return

    if study_area_type == "max_city":
        if not filename:
            raise ValueError("max_city study areas require --filename.")
        build_max_city_definitions(filename, definition_geographies, output_dir, definition_vintage or Path(definition_geographies).stem.split("_", 1)[0],
            cbsa_geographies=cbsa_geographies)
        return
    
    if not filename:
        raise ValueError("CBSA study areas require --filename.")

    metro_mappings = create_metro_mappings(fetch_metro_areas(filename))
    country = load_census_geography(definition_geographies)
    country["STATEFP"] = country["STATEFP"].astype(str).str.zfill(2)
    country["COUNTYFP"] = country["COUNTYFP"].astype(str).str.zfill(3)
    country["STCNTYFP"] = country["STATEFP"] + country["COUNTYFP"]

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for cbsa_code, cbsa in tqdm.tqdm(metro_mappings.items()):
        cbsa = add_cbsa_pop_and_geometry(country, cbsa)
        output_stem = f"{study_area_type}_{cbsa_code}_{definition_vintage}"
        with open(f"{output_dir}/{output_stem}.json", "w") as w:
            json.dump(area_to_dict(cbsa), w)
        cbsa.geometry.to_file(f"{output_dir}/{output_stem}.gpkg", driver="GPKG")


def fetch_metro_areas(filename) -> pd.DataFrame:
    """
    Reads the Census Bureau's CBSA Excel file (the delineation file), filters to Metropolitan Statistical Areas only, returns a df of CBSA-codes and FIPS rows
    """
    cbsa_counties = pd.read_excel(filename, skiprows=2)
    cbsa_counties = cbsa_counties[~cbsa_counties["FIPS County Code"].isna()]
    cbsa_counties["FIPS County Code"] = (
        cbsa_counties["FIPS County Code"]
        .astype(int)
        .astype(str)
        .str.zfill(3))
    cbsa_counties["FIPS State Code"] = (
        cbsa_counties["FIPS State Code"]
        .astype(int)
        .astype(str)
        .str.zfill(2))
    metro_areas = cbsa_counties[
        cbsa_counties["Metropolitan/Micropolitan Statistical Area"]
        == "Metropolitan Statistical Area"]
    return metro_areas


def create_metro_mappings(metro_areas: pd.DataFrame) -> dict[str, StudyArea]:
    """
    Groups metro area rows into a dict of cbsa_code mapped to CBSA objects, each holding a list of component county FIPS codes
    """
    metro_mappings = {}
    for _, row in metro_areas.iterrows():
        cbsa_code = row["CBSA Code"]
        cbsa_title = row["CBSA Title"]
        fips_code = row["FIPS State Code"] + row["FIPS County Code"]
        if cbsa_code in metro_mappings:
            metro_mappings[cbsa_code].component_counties_fips.append(fips_code)
        else:
            metro_mappings[cbsa_code] = StudyArea(area_code=cbsa_code, area_title=cbsa_title, component_counties_fips=[fips_code], total_population=None)
    return metro_mappings


def add_cbsa_pop_and_geometry(country: gpd.GeoDataFrame, cbsa: StudyArea) -> StudyArea:
    """
    Filters the national counties GDF to this CBSA's component counties, dissolves them into one polygon, sums population, then writes .gpkg and .json
    """
    assert cbsa.total_population is None

    cbsa_components = country[country["STCNTYFP"].apply(lambda x: x in cbsa.component_counties_fips)]

    cbsa.geometry = cbsa_components.dissolve()
    cbsa.total_population = int(cbsa_components["TOTPOP"].sum())

    assert cbsa.total_population is not None

    return cbsa


def first_existing_column(gdf: gpd.GeoDataFrame, candidates: list[str]) -> str:
    for col in candidates:
        if col in gdf.columns:
            return col
    raise ValueError(f"None of these columns were found: {', '.join(candidates)}")


def county_title(row: pd.Series) -> str:
    for col in ("NAMELSAD", "NAMELSAD20", "NAMELSAD10", "NAMELSAD00", "NAME"):
        if col in row and pd.notna(row[col]):
            return str(row[col])
    return f"County {row['STATEFP']}{row['COUNTYFP']}"


def build_county_definitions(definition_geographies: str, output_dir: str, definition_vintage: str) -> None:
    counties = load_census_geography(definition_geographies)
    state_col = first_existing_column(
        counties,
        ["STATEFP", "STATEFP20", "STATEFP10", "STATEFP00"])
    county_col = first_existing_column(
        counties,
        ["COUNTYFP", "COUNTYFP20", "COUNTYFP10", "COUNTYFP00"])
    counties["STATEFP"] = counties[state_col].astype(str).str.zfill(2)
    counties["COUNTYFP"] = counties[county_col].astype(str).str.zfill(3)
    counties["STCNTYFP"] = counties["STATEFP"] + counties["COUNTYFP"]

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    for _, county in tqdm.tqdm(counties.iterrows(), total=len(counties)):
        county_fips = county["STCNTYFP"]
        output_stem = f"county_{county_fips}_{definition_vintage}"
        county_gdf = gpd.GeoDataFrame(
            [county],
            columns=counties.columns,
            crs=counties.crs)
        study_area = StudyArea(
            area_code=county_fips,
            area_title=county_title(county),
            component_counties_fips=[county_fips],
            total_population=(
                int(county["TOTPOP"]) if "TOTPOP" in county and pd.notna(county["TOTPOP"]) else None
            ),
            geometry=county_gdf)

        with open(f"{output_dir}/{output_stem}.json", "w") as w:
            json.dump(area_to_dict(study_area), w)
        county_gdf.to_file(f"{output_dir}/{output_stem}.gpkg", driver="GPKG")


def build_max_county_definitions(filename: str, definition_geographies: str, output_dir: str, definition_vintage: str) -> None:
    
    metro_mappings = create_metro_mappings(fetch_metro_areas(filename))
    counties = load_census_geography(definition_geographies)

    counties["STATEFP"] = counties["STATEFP"].astype(str).str.zfill(2)
    counties["COUNTYFP"] = counties["COUNTYFP"].astype(str).str.zfill(3)
    counties["STCNTYFP"] = counties["STATEFP"] + counties["COUNTYFP"]

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for cbsa_code, cbsa in tqdm.tqdm(metro_mappings.items()):
        components = counties[counties["STCNTYFP"].isin(cbsa.component_counties_fips)]
        try: ##guard agains the extremely unlikely possibility of nonexistent counties in a cbsa.
            max_county = components.loc[components["TOTPOP"].idxmax()]
        except ValueError:
            print(f"CBSA {cbsa_code} contains no counties.", file=sys.stderr)
            continue
        county_fips = max_county["STCNTYFP"]

        output_stem = f"max_county_{county_fips}_{definition_vintage}"
        county_gdf = gpd.GeoDataFrame(
            [max_county],
            columns=counties.columns,
            crs=counties.crs,
        )
        study_area = StudyArea(
            area_code=county_fips,
            area_title=county_title(max_county),
            component_counties_fips=[county_fips],
            total_population=(
                int(max_county["TOTPOP"]) if "TOTPOP" in max_county and pd.notna(max_county["TOTPOP"]) else None),
            geometry=county_gdf)

        with open(f"{output_dir}/{output_stem}.json", "w") as w:
            json.dump(area_to_dict(study_area), w)
        county_gdf.to_file(f"{output_dir}/{output_stem}.gpkg", driver= "GPKG")


def build_max_city_definitions(filename: str, definition_geographies: str, output_dir: str, definition_vintage: str, cbsa_geographies: str = None) -> None:
    
    metro_mappings = create_metro_mappings(fetch_metro_areas(filename))
    places = load_census_geography(definition_geographies).to_crs("esri:102003")
    counties = load_census_geography(cbsa_geographies).to_crs("esri:102003")
    
    counties["STATEFP"] = counties["STATEFP"].astype(str).str.zfill(2)
    counties["COUNTYFP"] = counties["COUNTYFP"].astype(str).str.zfill(3)
    counties["STCNTYFP"] = counties["STATEFP"] + counties["COUNTYFP"]

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for cbsa_code, cbsa in tqdm.tqdm(metro_mappings.items()):
        components = counties[counties["STCNTYFP"].isin(cbsa.component_counties_fips)]
        cbsa_boundary = components.dissolve()

        places_in_cbsa = places[places.geometry.intersects(cbsa_boundary.union_all())]
        if places_in_cbsa.empty:
            print(f"No places found in CBSA {cbsa_code}. Skipping.")
            continue
        max_idx = places_in_cbsa["TOTPOP"].idxmax()
        max_place = places_in_cbsa.loc[[max_idx]]

        output_stem = f"max_city_{max_place['GEOID'].iloc[0]}_{definition_vintage}"

        study_area = StudyArea(
            area_code=max_place["GEOID"].iloc[0],
            area_title=str(max_place["NAMELSAD"].iloc[0]),
            component_counties_fips=[max_place["GEOID"].iloc[0]],
            total_population=(int(max_place["TOTPOP"].iloc[0]) if "TOTPOP" in max_place.columns and pd.notna(max_place["TOTPOP"].iloc[0]) else None),
            geometry=max_place)

        with open(f"{output_dir}/{output_stem}.json", "w") as w:
            json.dump(area_to_dict(study_area), w)
        max_place.to_file(f"{output_dir}/{output_stem}.gpkg", driver = "GPKG")


def area_to_dict(cbsa: StudyArea) -> dict:
    if hasattr(cbsa, "model_dump"):
        return cbsa.model_dump(exclude={"geometry"})
    return json.loads(cbsa.json(exclude={"geometry"}))


def load_census_geography(path_or_glob: str) -> gpd.GeoDataFrame:
    """
    Helper that accepts either a file path or a glob pattern, and loads + concatenates accordingly
    """
    p = Path(path_or_glob)
    if p.is_file():
        return gpd.read_file(p)
    files = sorted(p.parent.glob(p.name))
    if not files:
        raise FileNotFoundError(f"No files matching {path_or_glob}")
    frames = [gpd.read_file(f) for f in files]
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)

if __name__ == "__main__":
    typer.run(main)
