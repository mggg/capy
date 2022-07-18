import pandas as pd
import glob
import geopandas as gpd
import us
import tqdm
import typer

NHGIS_MAPPINGS = {
    "B18AA": "WHITE",
    "B18AB": "BLACK",
    "B18AC": "AMIN",
    "B18AD": "ASIAN",
    "B18AE": "2MORE",
}


def main():
    shapefiles = glob.glob("nhgis/**/**.shp")
    for filename in tqdm.tqdm(glob.glob("nhgis/**/**.csv")):
        year = filename.split("_")[-2]
        shapefile_matches = [x for x in shapefiles if f"tract_{year}" in x]
        assert len(shapefile_matches) == 1

        shapefile = gpd.read_file(shapefile_matches[0])
        df = pd.read_csv(filename, encoding_errors="replace")
        merged_gdf = shapefile.merge(
            df, left_on="GISJOIN", right_on=f"GJOIN{year}", suffixes=("", "_df")
        )
        merged_gdf = merged_gdf.rename(
            {k + year: v for k, v in NHGIS_MAPPINGS.items()}, axis=1
        )
        merged_gdf["TOTPOP"] = (
            merged_gdf[NHGIS_MAPPINGS.values()].dropna(axis=1).astype(int).sum(axis=1)
        )
        merged_gdf["POC"] = merged_gdf["TOTPOP"] - merged_gdf["WHITE"].astype(int)

        print(year, df.keys())
        print(
            year,
            df[f"B18AA{year}"][1:].astype(int).sum()
            - merged_gdf[f"WHITE"].astype(int).sum(),
        )

        merged_gdf.to_file(f"processed/{year}_tracts.shp")


if __name__ == "__main__":
    typer.run(main)
