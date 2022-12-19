import typer
import tqdm
import math
import glob
import geopandas as gpd
import sys


def main(source: str, target_glob: str, output_dir: str, prefix: str = ""):
    """
    Returns the subset of the source gdf that overlaps the target
    """
    source_gdf = gpd.read_file(source)
    source_area = source_gdf.unary_union.area
    for target in tqdm.tqdm(glob.glob(target_glob)):
        target_gdf = gpd.read_file(target).to_crs(source_gdf.crs)
        target_gdf_union = target_gdf.unary_union

        possible_intersects = source_gdf.iloc[
            source_gdf.sindex.query(target_gdf_union, predicate="intersects")
        ]
        overlaps = possible_intersects[
            possible_intersects["geometry"].apply(
                lambda x: (x.overlaps(target_gdf_union) or x.within(target_gdf_union))
                and not math.isclose(x.intersection(target_gdf_union).area, 0)
            )
        ]

        if len(overlaps) != 0:
            filename = target.split("/")[-1].split(".")[0]
            overlaps.to_file(f"{output_dir}/{prefix}{filename}_cbsa_tracts.shp")
            overlap_area = overlaps.unary_union.area
            print(f"{source}, {target}, {source_area}, {overlap_area}, {overlap_area/source_area}")
        else:
            print(
                "empty overlaps computed:", source, target, output_dir, file=sys.stderr
            )


if __name__ == "__main__":
    typer.run(main)
