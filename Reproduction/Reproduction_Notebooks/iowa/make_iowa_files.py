import pandas as pd
import geopandas as gpd
from census import Census
from us import states
from ipumspy import (
    IpumsApiClient,
    AggregateDataExtract,
    NhgisDataset,
)
from pathlib import Path
import glob
import zipfile
pd.set_option('display.max_columns', None) 
pd.set_option('display.max_rows', 50) 
import gerrychain
import networkx as nx

p1_population_columns_2010 = {
    "P001003": "WHITE",      # White alone
    "P001004": "BLACK",      # Black or African American alone
    "P001005": "AMIN",       # American Indian and Alaska Native alone
    "P001006": "ASIAN",      # Asian alone
    "P001007": "NHPI",       # Native Hawaiian and Other Pacific Islander alone
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

CENSUS_KEY = "7e1b79ce2adac634987a423b6d7fb99510fee50e"
FIPS = 19

census_2020 = Census(
    key=CENSUS_KEY,      # We use the provided Census API key.
    year=2020    # We specify that we would like to use the 2020 Census data.
)
census_2010 = Census(
    key=CENSUS_KEY,      # We use the provided Census API key.
    year=2010    # We specify that we would like to use the 2020 Census data.
)

# Iowa 2020 counties
ia_counties_2020 = gpd.read_file(
    "https://www2.census.gov/geo/tiger/TIGER2020/COUNTY/tl_2020_us_county.zip"
)
ia_counties_2020 = ia_counties_2020[ia_counties_2020["STATEFP"] == "19"]


# Iowa 2010 counties
ia_counties_2010 = gpd.read_file(
    "https://www2.census.gov/geo/tiger/TIGER2010/COUNTY/2010/tl_2010_us_county10.zip"
)
ia_counties_2010 = ia_counties_2010[ia_counties_2010["STATEFP10"] == "19"]

df_tracts_2010 = census_2010.pl.get(
    ("NAME", *p1_population_columns_2010),
    geo={
        "for": "county:*",
        "in": f"state:{FIPS}",
    }, 
)

df_tracts_2010 = pd.DataFrame(df_tracts_2010).rename(
    columns={"NAME": "name", **p1_population_columns_2010}
)

df_tracts_2020 = census_2020.pl.get(
    ("NAME", *p1_population_columns_2020),
    geo={
        "for": "county:*",
        "in": f"state:{FIPS}",
    }, 
)

df_tracts_2020 = pd.DataFrame(df_tracts_2020).rename(
    columns={"NAME": "name", **p1_population_columns_2020}
)

merged_gdf = ia_counties_2010.merge(
    df_tracts_2010, left_on="COUNTYFP10", right_on="county", suffixes=("", "_df")
    )

merged_gdf["BLACK"] = merged_gdf["BLACK"].astype(int)
merged_gdf["WHITE"] = merged_gdf["WHITE"].astype(int)
merged_gdf["TOTPOP"] = merged_gdf["TOTPOP"].astype(int)

merged_gdf["POC"] = merged_gdf["TOTPOP"] - merged_gdf["WHITE"].astype(int)

merged_gdf.to_file("reproduction_data/ia_files/ia_counties_2010.shp")
graph = gerrychain.Graph.from_wgeodataframe(merged_gdf)
graph.to_json(str(Path("reproduction_data/ia_files/ia_counties_2010.json").resolve()))


merged_gdf = ia_counties_2020.merge(
    df_tracts_2020, left_on="COUNTYFP", right_on="county", suffixes=("", "_df")
    )

merged_gdf["BLACK"] = merged_gdf["BLACK"].astype(int)
merged_gdf["WHITE"] = merged_gdf["WHITE"].astype(int)
merged_gdf["TOTPOP"] = merged_gdf["TOTPOP"].astype(int)

merged_gdf["POC"] = merged_gdf["TOTPOP"] - merged_gdf["WHITE"].astype(int)

merged_gdf.to_file("reproduction_data/ia_files/ia_counties_2020.shp")

graph = gerrychain.Graph.from_geodataframe(merged_gdf)
graph.to_json(str(Path("reproduction_data/ia_files/ia_counties_2020.json").resolve()))