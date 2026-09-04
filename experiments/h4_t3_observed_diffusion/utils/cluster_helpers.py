import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from shapely.ops import unary_union
import numpy as np

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from pipeline.metrics import moran, dissimilarity, half_edge

def compute_rho(G):
    """Black share of the whole graph: total BLACK / (total BLACK + total WHITE)"""
    total_black = sum(int(attrs["BLACK"]) for _, attrs in G.nodes(data=True))
    total_white = sum(int(attrs["WHITE"]) for _, attrs in G.nodes(data=True))
    return total_black / (total_black + total_white)

def compute_mean_node_rho(G):
    """computes the population unweighted mean of rho_i for all nodes i"""
    for node in G.nodes:
        G.nodes[node]["rho"] = G.nodes[node]["BLACK"]/(G.nodes[node]["WHITE"] + G.nodes[node]["BLACK"])
    return sum(attrs["rho"] for _, attrs in G.nodes(data=True))/len(G)

def compute_mass(G):
    """Black population of the whole graph"""
    total_black = sum(int(attrs["BLACK"]) for _, attrs in G.nodes(data=True))
    return total_black

def find_graph_files(graphs_path, city_code):
    graph_files = []
    for year in range(1980, 2021, 10):
        graph_file = graphs_path / str(year) / f"tracts_in_max_city_{city_code}_{year}_march_2020_vintage_connected.json"
        if not graph_file.exists():
            print(f"Graph file for year {year} does not exist.")
        graph_files.append(graph_file)
    return graph_files

def add_border_hops(G_city, n_edges=1):
    cluster_city_nodes = set(G_city.nodes) # local copy
    for _ in range(n_edges):
        cluster_city_nodes.update(# expand the copy, not the original
            neighbor for n in list(cluster_city_nodes) for neighbor in G_city_2020.neighbors(n))
    return G_city.subgraph(cluster_city_nodes).copy()

def plot_graph(G):
    pos = {node: (data["centroid_x"], data["centroid_y"]) for node, data in G.nodes(data=True)}
    if "BLACK" in G.nodes[list(G.nodes())[0]]:
        node_colors = [
            data["BLACK"] / (data["BLACK"] + data["WHITE"])
            if (data["BLACK"] + data["WHITE"]) > 0 else 0
            for node, data in G.nodes(data=True)]
    else:
        node_colors = [
            data["black_pop"] / (data["black_pop"] + data["white_pop"])
            if (data["black_pop"] + data["white_pop"]) > 0 else 0
            for node, data in G.nodes(data=True)]
    fig, ax = plt.subplots()
    nx.draw(G, pos, node_color=node_colors, cmap=plt.cm.Reds,
            with_labels=False, node_size=20, ax=ax)
    ax.axis("on") # re-enable the axes nx.draw hides
    ax.tick_params(left=True, bottom=True, labelleft=True, labelbottom=True)
    ax.set_xlabel("centroid_x")
    ax.set_ylabel("centroid_y")
    plt.show()

def get_geoids(gdf):
    """Extract GEOIDs from a GDF regardless of year-specific column naming."""
    if "GEOID" in gdf.columns:
        return set(gdf["GEOID"].astype(str))
    # earlier years don't have geoid, they use STATEFP00/COUNTYFP00/TRACTCE00
    state = next(c for c in gdf.columns if c.startswith("STATEFP"))
    county = next(c for c in gdf.columns if c.startswith("COUNTYFP"))
    tract = next(c for c in gdf.columns if c.startswith("TRACTCE"))
    return set((gdf[state] + gdf[county] + gdf[tract]).astype(str))

def back_project_cluster(gdf_cluster_2020, gdf_target, overlap_threshold=0.50):
    """
    Returns rows of gdf_target whose tract area overlaps > overlap_threshold with the dissolved 2020 cluster polygon.
    """
    if gdf_target.crs != gdf_cluster_2020.crs:
        gdf_target = gdf_target.to_crs(gdf_cluster_2020.crs)

    cluster_union = unary_union(gdf_cluster_2020.geometry)

    target = gdf_target.copy()
    target["_tract_area"] = target.geometry.area
    target["_inter_area"] = target.geometry.intersection(cluster_union).area
    target["_overlap"] = target["_inter_area"] / target["_tract_area"]

    return (target[target["_overlap"] > overlap_threshold]
        .drop(columns=["_tract_area", "_inter_area", "_overlap"])
        .copy())

def local_moran(graph, cluster_gisjoins):
    shares = np.array([
        graph.nodes[node]["BLACK"] / (graph.nodes[node]["BLACK"] + graph.nodes[node]["WHITE"])
        for node in graph.nodes()
    ])
    shares -= shares.mean()
    node_to_i = {node: i for i, node in enumerate(graph.nodes())}

    top_sum = 0
    bottom_sum = 0
    for i, node in enumerate(graph.nodes()):
        bottom_sum += shares[i] ** 2
        if graph.nodes[node]["GISJOIN"] in cluster_gisjoins:
            for nbr in graph.neighbors(node):
                top_sum += shares[i] * shares[node_to_i[nbr]]
    
    return len(graph)/len(graph.edges()) * (top_sum / bottom_sum)

def compute_cluster_metrics(cluster_graph, city_graph, year, label, metrics_by_year=None):
    # if metrics_by_year is None:
    #     metrics_by_year = {}
    for node in cluster_graph.nodes():
        cluster_graph.nodes[node]["white_plus_black"] = int(cluster_graph.nodes[node]["BLACK"]) + int(cluster_graph.nodes[node]["WHITE"])
    for node in city_graph.nodes():
        city_graph.nodes[node]["white_plus_black"] = int(city_graph.nodes[node]["BLACK"]) + int(city_graph.nodes[node]["WHITE"])

    city_mean_node_rho = compute_mean_node_rho(city_graph)

    metrics_by_year[(year, label)] = {}
    metrics_by_year[(year, label)]["moran"] = moran(cluster_graph, "BLACK", "white_plus_black")["moran_P"]
    metrics_by_year[(year, label)]["city_moran"] = moran(city_graph, "BLACK", "white_plus_black")["moran_P"]
    metrics_by_year[(year, label)]["dissimilarity"] = dissimilarity(cluster_graph, "BLACK", "WHITE", p=1)
    metrics_by_year[(year, label)]["city_dissimilarity"] = dissimilarity(city_graph, "BLACK", "WHITE", p=1)
    metrics_by_year[(year, label)]["half_edge"] = half_edge(cluster_graph, "BLACK", "WHITE")
    metrics_by_year[(year, label)]["city_half_edge"] = half_edge(city_graph, "BLACK", "WHITE")
    metrics_by_year[(year, label)]["amplitude"] = compute_mean_node_rho(cluster_graph) - city_mean_node_rho

    cluster_gisjoins = {attrs["GISJOIN"] for _, attrs in cluster_graph.nodes(data=True)}
    metrics_by_year[(year, label)]["local_moran"] = local_moran(city_graph, cluster_gisjoins)


    dropoff = 0
    nodes_by_gisjoin = {str(attrs["GISJOIN"]): n for n, attrs in city_graph.nodes(data=True)}
    selected_nodes = {nodes_by_gisjoin[g] for g in cluster_gisjoins if g in nodes_by_gisjoin}
    for node in selected_nodes:
        for neighbor in city_graph.neighbors(node):
            if neighbor not in selected_nodes:
                dropoff += (city_graph.nodes[neighbor]["rho"] - city_mean_node_rho) \
                        * (city_graph.nodes[node]["rho"] - city_mean_node_rho)
    metrics_by_year[(year, label)]["dropoff"] = dropoff

    return metrics_by_year

def calculate_cluster_spread(graph, gisjoins, fixed_center_gisjoin=None, distance = "euclidean"):
    """
    Calculates metrics for one supplied cluster-year area and core cluster.
    Parameters:
    graph: nx Graph. The dual graph for the CBSA and year of interest.
    gisjoins: a list of gisjoin IDs pointing to tracts
    distance: What distance function is used to calculate the spread. Can either be "graph", which 
    uses graph distance, or "euclidean", which uses the euclidean distance between cluster centroids.
    Returns:
    dict: A dictionary containing the calculated metrics for the catchment area and core cluster.
    """
    if distance not in ("euclidean", "graph"):
        raise ValueError
    nodes_by_gisjoin = {str(attrs["GISJOIN"]): n for n, attrs in graph.nodes(data=True)}
    selected_nodes = [nodes_by_gisjoin[g] for g in gisjoins if g in nodes_by_gisjoin]

    area_black_population = sum(int(graph.nodes[node]["BLACK"]) for node in selected_nodes)
    area_total_population = area_black_population + sum(int(graph.nodes[node]["WHITE"]) for node in selected_nodes)

    # Test every tract and pick the graph centroid. Centroid minimizes the sum of distances to all other tracts in the area, weighted by Black population.
    # If a fixed center is supplied (e.g. the buffer=0 medoid), use it directly so the medoid doesn't drift as buffers grow.
    nodes_by_gisjoin_lookup = {str(attrs["GISJOIN"]): n for n, attrs in graph.nodes(data=True)}
    if fixed_center_gisjoin is not None and fixed_center_gisjoin in nodes_by_gisjoin_lookup:
        best_center = nodes_by_gisjoin_lookup[fixed_center_gisjoin]
        if distance == "graph":
            distances = nx.single_source_shortest_path_length(graph, best_center)
        else: 
            cx = graph.nodes[best_center]["centroid_x"]
            cy = graph.nodes[best_center]["centroid_y"]
            distances = {
                node: np.sqrt(
                    (graph.nodes[node]["centroid_x"] - cx) ** 2 +
                    (graph.nodes[node]["centroid_y"] - cy) ** 2
                )
                for node in graph.nodes()
                }
        best_objective = sum(int(graph.nodes[node]["BLACK"]) * distances[node] for node in selected_nodes)
        best_distances = distances
    else:
        best_center = None
        best_objective = None
        best_distances = None
        for candidate in selected_nodes:
            if distance == "graph":
                distances = nx.single_source_shortest_path_length(graph, candidate)
            else:
                cx = graph.nodes[candidate]["centroid_x"]
                cy = graph.nodes[candidate]["centroid_y"]
                distances = {
                    node: np.sqrt(
                        (graph.nodes[node]["centroid_x"] - cx) ** 2 +
                        (graph.nodes[node]["centroid_y"] - cy) ** 2
                    )
                    for node in graph.nodes()
                    }
            objective = sum(int(graph.nodes[node]["BLACK"]) * distances[node] for node in selected_nodes)
            # The candidate tract itself contributes zero because its distance to itself is zero
            if best_objective is None or objective < best_objective:
                best_center = candidate
                best_objective = objective
                best_distances = distances

    #nball spread
    ball_target = 0.9 * area_black_population
    current_ball = 0
    n_ball_spread = None
    for node in sorted(selected_nodes, key=lambda node: best_distances[node]):
        current_ball += int(graph.nodes[node]["BLACK"])
        if current_ball >= ball_target:
            n_ball_spread = best_distances[node]
            break

    selected_subgraph = graph.subgraph(selected_nodes)

    return {
        "tract_count": len(selected_nodes),
        "component_count": nx.number_connected_components(selected_subgraph),
        "area_black_population": area_black_population,
        "area_total_population": area_total_population,
        "area_black_share": area_black_population / area_total_population,
        "spread": best_objective / area_black_population,
        "n_ball_spread": n_ball_spread,
        "center_node_id": best_center,
        "center_gisjoin": graph.nodes[best_center]["GISJOIN"],
        "center_geoid": graph.nodes[best_center].get("GEOID")}