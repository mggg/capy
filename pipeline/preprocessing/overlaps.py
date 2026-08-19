"""
This script finds which node units (e.g. tracts, blocks) fall within which study areas (e.g. cities, CBSAs). Process:
1. Find a bounding box of each state-level node units file and store.
2. For each study area, find which state-level bounding box oberlap.
3. Load only those files.
4. For these, calculate representative points per node unit. Select units whose representative point falls within the study area.
5. Save these geographies.
"""

import typer
import tqdm
import glob
import geopandas as gpd
import sys
from pathlib import Path
import fiona
import pandas as pd


def output_stem(study_area_file: str, prefix: str, census_geography_type: str, census_geography_year: str, definition_vintage: str) -> str:
    study_area_stem = Path(study_area_file).stem
    if census_geography_type and census_geography_year and definition_vintage:
        vintage_suffix = f"_{definition_vintage}"
        if not study_area_stem.endswith(vintage_suffix):
            raise ValueError(f"{study_area_file} does not end with vintage {definition_vintage}")
        study_area_identity = study_area_stem.removesuffix(vintage_suffix)
        return (f"{prefix}{census_geography_type}_in_{study_area_identity}_"
            f"{census_geography_year}_{definition_vintage}_vintage")
    return f"{prefix}{study_area_stem}_geographies"


def main(study_area_glob: str, output_dir: str, prefix: str = "", census_geography_type: str = "", census_geography_year: str = "", definition_vintage: str = "2020", census_geographies_dir: str = "data/processed/census_geographies"):
    """
    Writes census geographies whose representative points fall within each study area.
    """
    state_files = sorted((Path(census_geographies_dir) / census_geography_type).glob(f"{census_geography_year}_{census_geography_type}_*.gpkg"))
    # get 4 bounds of each state block collection
    state_bounds = []
    for f in state_files:
        with fiona.open(f) as src:
            if len(src) == 0:
                print("Skipping empty file:", f)
                continue
            state_bounds.append(src.bounds) # (minx, miny, maxx, maxy)

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    # for a city/CBSA file:
    for study_area_file in tqdm.tqdm(sorted(glob.glob(study_area_glob))):
        study_area_gdf = gpd.read_file(study_area_file).to_crs("esri:102003")
        study_area_boundary = study_area_gdf.union_all()
        minx, miny, maxx, maxy = study_area_boundary.bounds

        # select block files if their bounds are within study_area_boundary
        needed = [f for f, b in zip(state_files, state_bounds)
              if b[0] <= maxx and b[2] >= minx and b[1] <= maxy and b[3] >= miny]
        if not needed:
            print("no state files intersect", study_area_file, file=sys.stderr)
            continue
        state_fips = [f.stem.split("_")[-1] for f in needed]
        print(f"{Path(study_area_file).stem}: loading states {state_fips}", flush=True)

        frames = [gpd.read_file(f) for f in needed]
        census_geographies = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)

        geography_points = census_geographies.geometry.representative_point()
        geography_indices = geography_points.sindex.query(study_area_boundary, predicate="covers")
        selected_geographies = census_geographies.iloc[sorted(geography_indices)]

        if len(selected_geographies) != 0:
            selected_geographies_stem = output_stem(study_area_file, prefix, census_geography_type,census_geography_year, definition_vintage)
            selected_geographies.to_file(f"{output_dir}/{selected_geographies_stem}.gpkg", driver="GPKG")
        else:
            print("empty overlaps computed:", census_geographies_dir, study_area_file, output_dir, file=sys.stderr)


if __name__ == "__main__":
    typer.run(main)
