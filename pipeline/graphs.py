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
POPULATION_SUM_COLS = ("WHITE", "BLACK", "TOTPOP", "POC")


def main(input_glob: str, output_base_dir: str = "data/processed/dual_graphs", workers: int = 6, attr: str = "GISJOIN", pop_col: str = "TOTPOP"):
    gpkg_files = sorted(glob.glob(input_glob))
    worker = partial(_process_file, output_base_dir=output_base_dir, attr=attr, pop_col=pop_col)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        list(pool.map(worker, gpkg_files))


def _process_file(gpkg: str, output_base_dir: str, attr: str = "GISJOIN", pop_col: str = "TOTPOP"):
    year = Path(gpkg).parent.name
    stem = Path(gpkg).stem
    out_dir = Path(output_base_dir) / year
    out_dir.mkdir(parents=True, exist_ok=True)

    shp = gpd.read_file(gpkg)
    shp = shp.to_crs("esri:102003")  # so distances are in meters
    warnings.filterwarnings("ignore", message=".*NA values found in column.*")

    right = gpkg.split("_in_")[1]
    parts = right.split("_")
    area_code = parts[2] if parts[0] == "max" else parts[1]

    if shp.crs is None:
        raise ValueError(f"{gpkg} has no CRS defined.")

    centroids = shp.geometry.centroid
    try:
        graph = gerrychain.Graph.from_geodataframe(shp)
    except:
        shp["geometry"] = shp["geometry"].buffer(0)
        graph = gerrychain.Graph.from_geodataframe(shp)

    for idx in shp.index:
        graph.nodes[idx]["centroid_x"] = centroids.loc[idx].x
        graph.nodes[idx]["centroid_y"] = centroids.loc[idx].y

    graph.to_json(str(out_dir / f"{stem}_orig.json"))

    connected_graph = connect_components(shp, graph, attr)

    zero_nodes = []
    while len(connected_graph.nodes()) != 0 and has_zero_nodes(connected_graph):
        node_count = len(connected_graph.nodes())
        connected_graph, dropped_nodes = contract_zero_nodes(connected_graph)
        if len(connected_graph.nodes()) == node_count:
            print("No more zero nodes to contract. Remaining:", connected_graph.nodes())
            break
        for _, gisjoin in dropped_nodes:
            zero_nodes.append((area_code, gisjoin))

    connected_graph.to_json(str(out_dir / f"{stem}_connected.json"))

    dropped_dir = Path("data/processed/dropped_nodes") / year
    dropped_dir.mkdir(parents=True, exist_ok=True)
    if zero_nodes:
        pd.DataFrame(zero_nodes, columns=["area_code", "id"]).to_csv(
            dropped_dir / f"{stem}.csv", index=False)


def int_attr(attrs, col: str) -> int:
    value = attrs.get(col, 0)
    if value is None:
        return 0
    return int(value)


def node_contraction_population(graph: gerrychain.Graph, node) -> int:
    return sum(int_attr(graph.nodes[node], col) for col in CONTRACTION_POP_COLS)


def has_zero_nodes(graph: gerrychain.Graph):
    for node in graph.nodes():
        if node_contraction_population(graph, node) == 0:
            return True
    return False


def add_population_attrs(graph: gerrychain.Graph, target, source):
    for col in POPULATION_SUM_COLS:
        graph.nodes[target][col] = int_attr(graph.nodes[target], col) + int_attr(
            graph.nodes[source], col
        )


def contract_zero_nodes(graph: gerrychain.Graph):
    zero_nodes = [n for n in graph.nodes() if node_contraction_population(graph, n) == 0]

    dropped_nodes = [(n, graph.nodes[n].get("GISJOIN", n)) for n in zero_nodes]
    graph.remove_nodes_from(zero_nodes)

    return (graph, dropped_nodes)


def select_geom(shp: gpd.GeoDataFrame, geoid: str, attr: str = "GISJOIN"): 
    filtered_geoms = shp[shp[attr] == geoid]
    return filtered_geoms.iloc[0]["geometry"]


def distance(shp: gpd.GeoDataFrame, geoid_1: str, geoid_2: str, attr: str = "GISJOIN"):
    geom_1 = select_geom(shp, geoid_1, attr)
    geom_2 = select_geom(shp, geoid_2, attr)
    return geom_1.distance(geom_2)


def connect_components(shp: gpd.GeoDataFrame, graph: gerrychain.Graph, attr: str = "GISJOIN"):
    geom_by_geoid = dict(zip(shp[attr], shp.geometry))
    while nx.algorithms.components.number_connected_components(graph) != 1:
        print(
            "Connected components:",
            nx.algorithms.components.number_connected_components(graph),
        )
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
        pairs, distances = tree.query_nearest(
            island_geoms,
            return_distance=True,
            all_matches=False,
        )
        assert len(distances) > 0
        best_index = min(range(len(distances)), key=lambda index: distances[index])
        island_index = pairs[0][best_index]
        component_index = pairs[1][best_index]
        min_pair = (cc_geoids[0][component_index], cc_geoids[1][island_index])

        assert min_pair is not None
        graph.add_edge(geoid_node_mapping[min_pair[0]], geoid_node_mapping[min_pair[1]])
        print("Edge added:", min_pair)

    return graph


if __name__ == "__main__":
    typer.run(main)
