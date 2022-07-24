import geopandas as gpd
import typer
import os
import glob
import gerrychain
import networkx as nx
import matplotlib.pyplot as plt
from itertools import product
import tqdm
import functools


def main(filename: str, output_orig: str, output_connected: str):
    shp = gpd.read_file(filename)

    try:
        graph = gerrychain.Graph.from_geodataframe(shp)
    except:
        shp["geometry"] = shp["geometry"].buffer(0)
        graph = gerrychain.Graph.from_geodataframe(shp)

    graph.to_json(output_orig)

    connected_graph = connect_components(shp, graph)
    while len(connected_graph.nodes()) != 0 and has_zero_nodes(connected_graph):
        contract_zero_nodes(connected_graph)

    connected_graph.to_json(output_connected)


def has_zero_nodes(graph: gerrychain.Graph):
    for node in graph.nodes():
        if int(graph.nodes[node]["TOTPOP"]) == 0:
            return True
    return False


def contract_zero_nodes(graph: gerrychain.Graph):
    for node in graph.nodes():
        if int(graph.nodes[node]["TOTPOP"]) == 0:
            min_seen = 0
            min_neighbor = None

            for neighbor in graph.neighbors(node):
                pop = graph.nodes[neighbor]["TOTPOP"]
                if pop > min_seen:
                    min_seen = pop
                    min_neighbor = neighbor

            if min_seen != 0:
                print("contracted", node, neighbor)
                nx.contracted_nodes(graph, node, neighbor, self_loops=False, copy=False)
                break


def select_geom(shp: gpd.GeoDataFrame, geoid: str):
    filtered_geoms = shp[shp["GISJOIN"] == geoid]
    return filtered_geoms.iloc[0]["geometry"]


def distance(shp: gpd.GeoDataFrame, geoid_1: str, geoid_2: str):
    geom_1 = select_geom(shp, geoid_1)
    geom_2 = select_geom(shp, geoid_2)
    return geom_1.distance(geom_2)


def connect_components(shp: gpd.GeoDataFrame, graph: gerrychain.Graph):
    distance_cache = {}
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
                geoid = graph.nodes[node]["GISJOIN"]
                geoids.append(geoid)
                geoid_node_mapping[geoid] = node

            cc_geoids.append(geoids)

        # Find shortest path, very inefficient O(n^2)
        min_distance = None
        min_pair = None
        assert len(cc_geoids) == 2
        for geoid_pair in tqdm.tqdm(
            product(cc_geoids[0], cc_geoids[1]),
            total=len(cc_geoids[0]) * len(cc_geoids[1]),
        ):
            geoid_1, geoid_2 = geoid_pair

            if geoid_pair in distance_cache:
                calc_distance = geoid_pair
            else:
                calc_distance = distance(shp, geoid_1, geoid_2)

            distance_cache[geoid_pair] = calc_distance
            distance_cache[tuple(reversed(geoid_pair))] = calc_distance

            if min_distance is None or calc_distance < min_distance:
                min_distance = calc_distance
                min_pair = (geoid_1, geoid_2)

        assert min_pair is not None
        graph.add_edge(geoid_node_mapping[min_pair[0]], geoid_node_mapping[min_pair[1]])
        print("Edge added:", min_pair)

    return graph


if __name__ == "__main__":
    typer.run(main)
