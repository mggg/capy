import typer
import tqdm
import glob
import geopandas as gpd
import sys
from pathlib import Path

# for flexibility with different versions of geopandas
def union_geometry(gdf: gpd.GeoDataFrame):
    geometry = gdf.geometry
    if hasattr(geometry, "union_all"):
        return geometry.union_all()
    return geometry.unary_union


def main(tracts_file: str, cbsa_glob: str, output_dir: str, prefix: str = ""):
    """
    Writes tracts whose representative points fall within each CBSA.
    """
    tracts_gdf = gpd.read_file(tracts_file)
    tract_points = tracts_gdf.geometry.representative_point()
    all_tracts_area = union_geometry(tracts_gdf).area

    for cbsa_file in tqdm.tqdm(sorted(glob.glob(cbsa_glob))):
        cbsa_gdf = gpd.read_file(cbsa_file).to_crs(tracts_gdf.crs)
        cbsa_boundary = union_geometry(cbsa_gdf)

        tract_indices = tract_points.sindex.query(
            cbsa_boundary, predicate="contains")
        cbsa_tracts = tracts_gdf.iloc[sorted(tract_indices)]

        if len(cbsa_tracts) != 0:
            cbsa_name = Path(cbsa_file).stem
            cbsa_tracts.to_file(
                f"{output_dir}/{prefix}{cbsa_name}_cbsa_tracts.shp")
            cbsa_tracts_area = union_geometry(cbsa_tracts).area
            print(
                f"{tracts_file}, {cbsa_file}, {all_tracts_area}, "
                f"{cbsa_tracts_area}, {cbsa_tracts_area/all_tracts_area}")
        else:
            print(
                "empty overlaps computed:",
                tracts_file,
                cbsa_file,
                output_dir,
                file=sys.stderr)


if __name__ == "__main__":
    typer.run(main)
