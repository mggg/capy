"""
Create dual graphs of given geometries and save: (1) the original dual graph (2) an edited graph, dropping 0-population nodes and connecting disconnected components.
"""

import glob
import geopandas as gpd
import pandas as pd
import typer
import warnings
import gerrychain
import networkx as nx
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from shapely.strtree import STRtree
from pathlib import Path

CONTRACTION_POP_COLS = ("WHITE", "BLACK")


def main(input_glob: str, output_base_dir: str = "data/processed/dual_graphs", workers: int = 6, attr: str = "GISJOIN"):
    gpkg_files = sorted(glob.glob(input_glob))
    if not gpkg_files:
        raise

    worker = partial(_process_file, output_base_dir=output_base_dir, attr=attr)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(worker, gpkg_files))

    # infer run output dir from the first matched file's stem:
    # e.g. "tracts_in_max_city_35620_2020_vintage" to outputs/tracts_in_max_city/
    stem = Path(gpkg_files[0]).stem
    census_geography_type = stem.split("_in_", 1)[0]
    right_parts = stem.split("_in_", 1)[1].split("_")
    study_area_type = f"max_{right_parts[1]}" if right_parts[0] == "max" else right_parts[0]
    dropped_nodes_dir = Path("outputs") / f"{census_geography_type}_in_{study_area_type}" / "dropped_nodes"

    # aggregate dropped nodes by year and write one gpkg per year
    by_year = {}
    for year, dropped_gdf in results:
        if dropped_gdf is not None:
            by_year.setdefault(year, []).append(dropped_gdf)
    for year, gdfs in by_year.items():
        combined = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), crs=gdfs[0].crs)
        dropped_nodes_dir.mkdir(parents=True, exist_ok=True)
        combined.to_file(dropped_nodes_dir / f"dropped_nodes_{year}.gpkg", driver="GPKG")


def _process_file(gpkg: str, output_base_dir: str, attr: str = "GISJOIN"):
    # derive output paths from the filename:
    year = Path(gpkg).parent.name
    stem = Path(gpkg).stem
    out_dir = Path(output_base_dir) / year
    out_dir.mkdir(parents=True, exist_ok=True)

    # read and reproject
    geofile = gpd.read_file(gpkg)
    geofile = geofile.to_crs("esri:102003") # so distances are in meters
    warnings.filterwarnings("ignore", message=".*NA values found in column.*")  # some fields were introduced in 2000, so they're NA in earlier years. It's expected.
    warnings.filterwarnings("ignore", message=".*Found islands.*")  # degree-0 nodes are handled explicitly by connect_components.

    # extract area code from the filename
    right = gpkg.split("_in_")[1]
    parts = right.split("_")
    area_code = parts[2] if parts[0] == "max" else parts[1]

    if geofile.crs is None:
        raise ValueError(f"{gpkg} has no CRS defined.")

    # build a dual graph
    try:
        graph = gerrychain.Graph.from_geodataframe(geofile)
    except:
        geofile["geometry"] = geofile["geometry"].buffer(0)
        graph = gerrychain.Graph.from_geodataframe(geofile)

    # attach centroid coordinates to each node
    centroids = geofile.geometry.centroid
    for idx in geofile.index:
        graph.nodes[idx]["centroid_x"] = centroids.loc[idx].x
        graph.nodes[idx]["centroid_y"] = centroids.loc[idx].y

    graph.to_json(str(out_dir / f"{stem}_orig.json"))

    # create an edited version of the graph:
    # if the graph has disconnected components, add an edge across the nearest pair of geometries
    connected_graph, n_edges_added = connect_components(geofile, graph, attr)

    # remove 0-population nodes and their edges
    dropped_indices = []
    while len(connected_graph.nodes()) != 0 and has_zero_nodes(connected_graph):
        node_count = len(connected_graph.nodes())
        connected_graph, dropped = drop_zero_nodes(connected_graph)
        if len(connected_graph.nodes()) == node_count:
            break
        dropped_indices.extend(n for n, _ in dropped)

    if n_edges_added > 0 or len(dropped_indices) > 0:
        print(f"{stem}: +{n_edges_added} edges, {len(dropped_indices)} zero-pop nodes dropped", flush=True)
        
    connected_graph.to_json(str(out_dir / f"{stem}_connected.json"))

    if dropped_indices:
        dropped_gdf = geofile.loc[dropped_indices].copy()
        dropped_gdf["area_code"] = area_code
        return year, dropped_gdf
    return year, None


def int_attr(attrs, col: str) -> int:
    value = attrs.get(col, 0)
    if value is None:
        return 0
    return int(value)


def node_contraction_population(graph: gerrychain.Graph, node) -> int:
    return sum(int_attr(graph.nodes[node], col) for col in CONTRACTION_POP_COLS)


def has_zero_nodes(graph: gerrychain.Graph):
    for node in graph.nodes():
        node_contraction_population = sum(int_attr(graph.nodes[node], col) for col in CONTRACTION_POP_COLS)
        if node_contraction_population == 0:
            return True
    return False


def drop_zero_nodes(graph: gerrychain.Graph):
    zero_nodes = [n for n in graph.nodes() if node_contraction_population(graph, n) == 0]

    dropped_nodes = [(n, graph.nodes[n].get("GISJOIN", n)) for n in zero_nodes]
    graph.remove_nodes_from(zero_nodes)

    return (graph, dropped_nodes)


def connect_components(geofile: gpd.GeoDataFrame, graph: gerrychain.Graph, attr: str = "GISJOIN"):
    geom_by_geoid = dict(zip(geofile[attr], geofile.geometry))
    n_added = 0
    while nx.algorithms.components.number_connected_components(graph) != 1:
        cc = list(nx.connected_components(graph))[:2]
        assert len(cc) == 2
        cc_geoids = []
        geoid_node_mapping = {}

        # Convert to GEOIDs
        for component in cc:
            geoids = []

            for node in component:
                geoid = graph.nodes[node][attr]
                geoids.append(geoid)
                geoid_node_mapping[geoid] = node

            cc_geoids.append(geoids)

        # Find the nearest pair between the two components using a spatial index.
        assert len(cc_geoids) == 2
        component_geoms = [geom_by_geoid[geoid] for geoid in cc_geoids[0]]
        island_geoms = [geom_by_geoid[geoid] for geoid in cc_geoids[1]]
        tree = STRtree(component_geoms)
        pairs, distances = tree.query_nearest(island_geoms, return_distance=True,
                                              all_matches=False)
        assert len(distances) > 0
        best_index = min(range(len(distances)), key=lambda index: distances[index])
        island_index = pairs[0][best_index]
        component_index = pairs[1][best_index]
        min_pair = (cc_geoids[0][component_index], cc_geoids[1][island_index])

        assert min_pair is not None
        graph.add_edge(geoid_node_mapping[min_pair[0]], geoid_node_mapping[min_pair[1]])
        n_added += 1

    return graph, n_added


if __name__ == "__main__":
    typer.run(main)
