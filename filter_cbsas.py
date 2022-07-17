from definitions import CBSA, CBSADict

import multiprocessing
from shapely.ops import unary_union
from typing import Dict
import tqdm
import pandas as pd
import typer
import geopandas as gpd
import json
import os


def main(filename: str = "list1_2020.xls"):
    metro_areas = fetch_metro_areas(filename)
    mappings_without_pops = create_metro_mappings(metro_areas)
    # mappings_without_pops = dict(list(mappings_without_pops.items())[:3])
    country = gpd.read_file("processed/2020_tracts.shp")
    country["STCNTYFP"] = country["STATEFP"] + country["COUNTYFP"]

    metros = {
        k: add_cbsa_pop_and_geometry(country, v)
        for k, v in tqdm.tqdm(mappings_without_pops.items())
    }
    # with multiprocessing.Pool(multiprocessing.cpu_count()) as p:
    #     f = lambda x: (x[0], add_cbsa_pop_and_geometry(country, x[1]))
    #     metros_with_pops = dict(p.imap(f, mappings_without_pops.items()))

    for cbsa_code, cbsa in metros.items():
        with open(f"cbsas/defs/{cbsa.total_population}_{cbsa_code}.json", "w") as w:
            json.dump(cbsa.json(exclude={"geometry": True}), w)

        cbsa.geometry.to_file(f"cbsas/defs/{cbsa.total_population}_{cbsa_code}.shp")


def fetch_metro_areas(filename: str = "list1_2020.xls") -> pd.DataFrame:
    cbsa_counties = pd.read_excel(filename, skiprows=2)
    cbsa_counties = cbsa_counties[~cbsa_counties["FIPS County Code"].isna()]
    cbsa_counties["FIPS County Code"] = (
        cbsa_counties["FIPS County Code"]
        .astype(int)
        .astype(str)
        .apply(lambda x: x.zfill(3))
    )
    cbsa_counties["FIPS State Code"] = (
        cbsa_counties["FIPS State Code"]
        .astype(int)
        .astype(str)
        .apply(lambda x: x.zfill(2))
    )
    metro_areas = cbsa_counties[
        cbsa_counties["Metropolitan/Micropolitan Statistical Area"]
        == "Metropolitan Statistical Area"
    ]
    return metro_areas


def create_metro_mappings(metro_areas: pd.DataFrame) -> Dict[str, CBSA]:
    metro_mappings = {}
    for c, row in metro_areas.iterrows():
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
    assert cbsa.total_population == None

    cbsa_components = country[
        country["STCNTYFP"].apply(lambda x: x in cbsa.component_counties_fips)
    ]

    cbsa.geometry = cbsa_components.dissolve()
    cbsa.total_population = int(cbsa_components["TOTPOP"].sum())

    assert cbsa.total_population != None

    return cbsa


if __name__ == "__main__":
    typer.run(main)
