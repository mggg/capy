"""
This script downloads Iowa county shapefiles and Census PL 94-171 race data for 2010 and 2020, merges them into GeoDataFrames, and saves GerryChain-compatible adjacency graph JSON files and shapefiles for use in downstream Iowa experiments.
Global Parameters:
    CENSUS_KEY: str
        A valid Census Bureau API key required to fetch PL 94-171 data
    FIPS: int
        The state FIPS code for Iowa (19)
"""
import typer
import pandas as pd
import geopandas as gpd
from census import Census
from pathlib import Path
import gerrychain
import os

CENSUS_KEY = os.environ.get("CENSUS_API_KEY")
if CENSUS_KEY is None:
    raise EnvironmentError("CENSUS_API_KEY environment variable is not set")
FIPS = "19" #iowa fips code

#population data for 2010, and 2020
p1_population_columns_2010 = {
    "P001003": "WHITE",      # White alone
    "P001004": "BLACK",      # Black or African American alone
    "P001005": "AMIN",       # American Indian and Alaska Native alone
    "P001006": "ASIAN",      # Asian alone
    "P001007": "NHPI",       # Native Hawaiian and Other Pacifi Islander alone
    "P001008": "OTHER",     # Some Other Race alone
    "P001009": "2MORE",     # Two or more races
    "P001001": "TOTPOP"     #Total Population            
}

p1_population_columns_2020 = {
    "P1_003N": "WHITE",         # White alone
    "P1_004N": "BLACK",         # Black or African American alone
    "P1_005N": "AMIN",          # American Indian and Alaska Native alone
    "P1_006N": "ASIAN",         # Asian alone
    "P1_007N": "NHPI",          # Native Hawaiian and Other Pacific Islander alone
    "P1_008N": "OTHER",     # Some Other Race alone
    "P1_009N": "2MORE",     # Two or more races
    "P1_001N" : "TOTPOP"  #Total Population        
}

def main():
    """
    Downloads, merges, and exports Iowa county shapefiles and Census PL 94-171 data for 2010 and 2020.
    Writes GerryChain-compatible JSON adjacency graphs and shapefiles to data/experiment_specific/ia_files/.
    """
    #writing graph jsons and shapefiles, 2020
    merged_2020 = make_iowa_gdf(2020, p1_population_columns_2020)
    merged_2020.to_file("data/experiment_specific/ia_files/ia_counties_2020.shp")
    graph = gerrychain.Graph.from_geodataframe(merged_2020)
    graph.to_json(str(Path("data/experiment_specific/ia_files/ia_counties_2020.json").resolve()))

    #writing graph jsons and shapefiles, 2010
    merged_2010 = make_iowa_gdf(2010, p1_population_columns_2010)
    merged_2010.to_file("data/experiment_specific/ia_files/ia_counties_2010.shp")
    graph = gerrychain.Graph.from_geodataframe(merged_2010)
    graph.to_json(str(Path("data/experiment_specific/ia_files/ia_counties_2010.json").resolve()))

def make_iowa_gdf(year, popcolumns):
    """
    Downloads Iowa county shapefiles and Census PL 94-171 population data for a given year,
    merges them into a GeoDataFrame, and adds a POC column.
    Parameters:
        year: int
            Census year; must be 2010 or 2020.
        popcolumns: dict
            Mapping of Census variable codes to readable column names (e.g. {"P1_001N": "TOTPOP"}).
    Returns:
        merged_gdf: GeoDataFrame
            Iowa county GeoDataFrame with population columns WHITE, BLACK, TOTPOP, POC, and geometry.
    Raises:
        ValueError: if county keys in the shapefile and Census data do not match before merging.
    """
    #handles naming discrepancies between years
    YEAR_CONFIG = {
    2010: {
        "url": "https://www2.census.gov/geo/tiger/TIGER2010/COUNTY/2010/tl_2010_us_county10.zip",
        "statefp_col": "STATEFP10",
        "countyfp_col": "COUNTYFP10",
    },
    2020: {
        "url": "https://www2.census.gov/geo/tiger/TIGER2020/COUNTY/tl_2020_us_county.zip",
        "statefp_col": "STATEFP",
        "countyfp_col": "COUNTYFP",
    },}
   
    census = Census(
        key=CENSUS_KEY,      
        year=year   
        )

    counties = gpd.read_file(
        YEAR_CONFIG[year]["url"]
        )
   
    ia_counties = counties[counties[YEAR_CONFIG[year]["statefp_col"]] == FIPS]


    df_counties = census.pl.get(
        ("NAME", *popcolumns),
        geo={
            "for": "county:*",
            "in": f"state:{FIPS}",
        }, 
        )
    df_counties = pd.DataFrame(df_counties).rename(
    columns={"NAME": "name", **popcolumns}
    )
    
    shp_keys = set(ia_counties[YEAR_CONFIG[year]["countyfp_col"]])
    census_keys = set(df_counties["county"])

    if shp_keys != census_keys:
        raise ValueError(
            f"County key mismatch before {year} merge — "
            f"in shapefile only: {shp_keys - census_keys}, "
            f"in census only: {census_keys - shp_keys}"
        )
    #merging data with shapefiles
    merged_gdf = ia_counties.merge(
        df_counties, left_on=YEAR_CONFIG[year]["countyfp_col"], right_on="county", 
        suffixes=("", "_df"), validate = "one_to_one"
        )

    #makeing demographic dataframe columns legible for later scripts
    merged_gdf["BLACK"] = merged_gdf["BLACK"].astype(int)
    merged_gdf["WHITE"] = merged_gdf["WHITE"].astype(int)
    merged_gdf["TOTPOP"] = merged_gdf["TOTPOP"].astype(int)

    merged_gdf["POC"] = merged_gdf["TOTPOP"] - merged_gdf["WHITE"].astype(int)

    return merged_gdf

if __name__ == "__main__":
    typer.run(main)

