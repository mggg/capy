import typer
import geopandas as gpd

def main(source: str, target: str, output: str):
    """
    Returns the subset of the source gdf that intersects the target
    """
    source_gdf = gpd.read_file(source)
    target_gdf = gpd.read_file(target)
    target_gdf_union = target_gdf.unary_union

    possible_intersects = source_gdf.iloc[source_gdf.sindex.query(target_gdf_union, predicate="contains")]
    intersects = possible_intersects[possible_intersects["geometry"].apply(lambda x: x.intersects(target_gdf_union))]
    intersects.to_file(output)


if __name__ == "__main__":
    typer.run(main)
