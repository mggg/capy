import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.utils.definitions import CBSA

import tqdm
import pandas as pd
import typer
import geopandas as gpd
import json
from pathlib import Path


def cbsa_to_dict(cbsa: CBSA) -> dict:
    if hasattr(cbsa, "model_dump"):
        return cbsa.model_dump(exclude={"geometry"})
    return json.loads(cbsa.json(exclude={"geometry"}))


def main(
    filename: str = "",
    definition_geographies: str = "data/interim/census_geographies/2020_tracts.shp",
    output_dir: str = "data/interim/study_areas/definitions",
    study_area_type: str = "cbsa",
    definition_vintage: str = "",
):
    if study_area_type == "counties":
        study_area_type = "county"
    if study_area_type not in {"cbsa", "county"}:
        raise ValueError(
            f"Unsupported study area type {study_area_type!r}. "
            "Use 'cbsa' or 'county'."
        )

    if study_area_type == "county":
        build_county_definitions(
            definition_geographies,
            output_dir,
            definition_vintage or Path(definition_geographies).stem.split("_", 1)[0],
        )
        return

    if not filename:
        raise ValueError("CBSA study areas require --filename.")

    source_stem = Path(filename).stem
    if not definition_vintage:
        if source_stem.startswith("list1_"):
            definition_vintage = source_stem.removeprefix("list1_")
        elif source_stem.startswith(f"{study_area_type}_"):
            definition_vintage = source_stem.removeprefix(f"{study_area_type}_")
        else:
            definition_vintage = source_stem

    metro_mappings = create_metro_mappings(fetch_metro_areas(filename))
    country = gpd.read_file(definition_geographies)
    country["STATEFP"] = country["STATEFP"].astype(str).str.zfill(2)
    country["COUNTYFP"] = country["COUNTYFP"].astype(str).str.zfill(3)
    country["STCNTYFP"] = country["STATEFP"] + country["COUNTYFP"]

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for cbsa_code, cbsa in tqdm.tqdm(metro_mappings.items()):
        cbsa = add_cbsa_pop_and_geometry(country, cbsa)
        output_stem = f"{study_area_type}_{cbsa_code}_{definition_vintage}"
        with open(f"{output_dir}/{output_stem}.json", "w") as w:
            json.dump(cbsa_to_dict(cbsa), w)
        cbsa.geometry.to_file(f"{output_dir}/{output_stem}.shp")


def fetch_metro_areas(filename) -> pd.DataFrame:
    cbsa_counties = pd.read_excel(filename, skiprows=2)
    cbsa_counties = cbsa_counties[~cbsa_counties["FIPS County Code"].isna()]
    cbsa_counties["FIPS County Code"] = (
        cbsa_counties["FIPS County Code"]
        .astype(int)
        .astype(str)
        .str.zfill(3)
    )
    cbsa_counties["FIPS State Code"] = (
        cbsa_counties["FIPS State Code"]
        .astype(int)
        .astype(str)
        .str.zfill(2)
    )
    metro_areas = cbsa_counties[
        cbsa_counties["Metropolitan/Micropolitan Statistical Area"]
        == "Metropolitan Statistical Area"
    ]
    return metro_areas


def create_metro_mappings(metro_areas: pd.DataFrame) -> dict[str, CBSA]:
    metro_mappings = {}
    for _, row in metro_areas.iterrows():
        cbsa_code = row["CBSA Code"]
        cbsa_title = row["CBSA Title"]
        fips_code = row["FIPS State Code"] + row["FIPS County Code"]
        if cbsa_code in metro_mappings:
            metro_mappings[cbsa_code].component_counties_fips.append(fips_code)
        else:
            metro_mappings[cbsa_code] = CBSA(
                cbsa_code=cbsa_code,
                cbsa_title=cbsa_title,
                component_counties_fips=[fips_code],
                total_population=None,
            )

    return metro_mappings


def add_cbsa_pop_and_geometry(country: gpd.GeoDataFrame, cbsa: CBSA) -> CBSA:
    assert cbsa.total_population is None

    cbsa_components = country[
        country["STCNTYFP"].apply(lambda x: x in cbsa.component_counties_fips)
    ]

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


def build_county_definitions(
    definition_geographies: str,
    output_dir: str,
    definition_vintage: str,
) -> None:
    counties = gpd.read_file(definition_geographies)
    state_col = first_existing_column(
        counties,
        ["STATEFP", "STATEFP20", "STATEFP10", "STATEFP00"],
    )
    county_col = first_existing_column(
        counties,
        ["COUNTYFP", "COUNTYFP20", "COUNTYFP10", "COUNTYFP00"],
    )
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
            crs=counties.crs,
        )
        study_area = CBSA(
            cbsa_code=county_fips,
            cbsa_title=county_title(county),
            component_counties_fips=[county_fips],
            total_population=(
                int(county["TOTPOP"]) if "TOTPOP" in county and pd.notna(county["TOTPOP"]) else None
            ),
            geometry=county_gdf,
        )

        with open(f"{output_dir}/{output_stem}.json", "w") as w:
            json.dump(cbsa_to_dict(study_area), w)
        county_gdf.to_file(f"{output_dir}/{output_stem}.shp")


if __name__ == "__main__":
    typer.run(main)
