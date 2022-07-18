import typer
import geopandas as gpd
import sys


def main(source: str, target: str, output: str):
    """
    Returns the subset of the source gdf that intersects the target
    """
    source_gdf = gpd.read_file(source)
    target_gdf = gpd.read_file(target)
    target_gdf_union = target_gdf.unary_union

    possible_intersects = source_gdf.iloc[
        source_gdf.sindex.query(target_gdf_union, predicate="intersects")
    ]
    intersects = possible_intersects[
        possible_intersects["geometry"].apply(lambda x: x.intersects(target_gdf_union))
    ]

    if len(intersects) != 0:
        intersects.to_file(output)
    else:
        print("empty intersection computed:", source, target, output, file=sys.stderr)


if __name__ == "__main__":
    typer.run(main)
