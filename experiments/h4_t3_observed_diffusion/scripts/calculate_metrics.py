# Calculate metrics for cluster-years area and save
from pathlib import Path
import networkx as nx
import pandas as pd
import gerrychain

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
SELECTIONS = EXPERIMENT_DIR / "data" / "auto_cluster_tracts.csv"
# SELECTIONS = EXPERIMENT_DIR / "data" / "cluster_graphs_buffers"
GRAPH_DIR = EXPERIMENT_DIR.parent.parent / "data" / "processed" / "dual_graphs"
OUTPUT = EXPERIMENT_DIR / "data" / "cluster_metrics.csv"
# OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"
geography = "max_city"

def calculate_cluster_spread(graph, gisjoins):
    """
    Calculates metrics for one supplied cluster-year area and core cluster.
    Parameters:
    ----------
    graph: nx Graph
        The dual graph for the CBSA and year of interest.
    Returns
    -------
    dict
        A dictionary containing the calculated metrics for the catchment area and core cluster.
    """
    nodes_by_gisjoin = {str(attrs["GISJOIN"]): n for n, attrs in graph.nodes(data=True)}
    selected_nodes = [nodes_by_gisjoin[g] for g in gisjoins if g in nodes_by_gisjoin]

    area_black_population = sum(int(graph.nodes[node]["BLACK"]) for node in selected_nodes)
    area_white_population = sum(int(graph.nodes[node]["WHITE"]) for node in selected_nodes)
    area_total_population = sum(int(graph.nodes[node]["TOTPOP"]) for node in selected_nodes)

    city_black_population = sum(int(graph.nodes[node]["BLACK"]) for node in graph.nodes)
    city_white_population = sum(int(graph.nodes[node]["WHITE"]) for node in graph.nodes)
    city_total_population = sum(int(graph.nodes[node]["TOTPOP"]) for node in graph.nodes)

    for node in graph.nodes:
        graph.nodes[node]["rho"] = graph.nodes[node]["BLACK"]/(graph.nodes[node]["WHITE"] + graph.nodes[node]["BLACK"])
    city_mean_node_rho = sum(attrs["rho"] for _, attrs in graph.nodes(data=True))/len(graph)

    for node in selected_nodes:
        graph.nodes[node]["rho"] = graph.nodes[node]["BLACK"]/(graph.nodes[node]["WHITE"] + graph.nodes[node]["BLACK"])
    area_mean_node_rho = sum(graph.nodes[n]["rho"] for n in selected_nodes)/len(selected_nodes)


    dropoff = 0
    selected_set = set(selected_nodes) #makes looking up if neighbor is selected easier
    for node in selected_nodes:
        for neighbor in graph.neighbors(node):
            if neighbor not in selected_set:
                dropoff += (graph.nodes[neighbor]["rho"] - city_mean_node_rho) * (graph.nodes[node]["rho"] - city_mean_node_rho)


    # Test every tract and pick the graph centroid. Centroid minimizes the sum of distances to all other tracts in the area, weighted by Black population.
    best_center = None
    best_objective = None
    for candidate in selected_nodes:
        distances = nx.single_source_shortest_path_length(graph, candidate)
        objective = sum(int(graph.nodes[node]["BLACK"]) * distances[node] for node in selected_nodes)
        # The candidate tract itself contributes zero because its distance to itself is zero
        # tie_break = str(graph.nodes[candidate]["GISJOIN"])
        if best_objective is None or objective < best_objective: # (objective, tie_break) < (best_objective, str(graph.nodes[best_center]["GISJOIN"])):
            best_center = candidate
            best_objective = objective

    selected_subgraph = graph.subgraph(selected_nodes)
    return {
        "tract_count": len(selected_nodes),
        "component_count": nx.number_connected_components(selected_subgraph),
        "area_black_population": area_black_population,
        "area_total_population": area_total_population,
        "area_black_share": area_black_population / area_total_population,
        "cluster_rho": area_black_population / (area_black_population + area_white_population),
        "city_rho": city_black_population / (city_black_population + city_white_population),
        "city_mean_node_rho": city_mean_node_rho,
        "cluster_mean_node_rho": area_mean_node_rho,
        "dropoff": dropoff,
        "spread": best_objective / area_black_population,
        "center_node_id": best_center,
        "center_gisjoin": graph.nodes[best_center]["GISJOIN"],
        "center_geoid": graph.nodes[best_center].get("GEOID")
        }


selection_df = pd.read_csv(SELECTIONS, dtype={"cbsa": str, "year": int, "cluster": str, "gisjoin": str}).rename(columns={"cbsa": "area_code"})
selection_df = selection_df[selection_df["area_code"].isin(["16980", "37980"])]



output_rows = []

for (area_code, year, cluster), group in selection_df.groupby(["area_code", "year", "cluster"], sort=True):
    print(f"Calculating metrics for area_code {area_code}, year {year}, cluster {cluster}.")
    if geography == "max_city":
        CBSA_TO_MAX_CITY = {
            "16980": "1714000",
            "37980": "4260000",
            "33100": "1245000"
        }

        area_code = CBSA_TO_MAX_CITY[area_code]

    matches = sorted(
        (GRAPH_DIR / str(year)).glob(f"tracts_in_{geography}_{area_code}_{year}_*_connected.json"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one city graph for area_code {area_code} in {year}, but found {len(matches)}.")
    graph = gerrychain.Graph.from_json(matches[0])

    metrics = calculate_cluster_spread(graph, gisjoins=group["gisjoin"].tolist())

    output_rows.append({"area_code": area_code, "year": year, "cluster": cluster, **metrics})

pd.DataFrame(output_rows).sort_values(["area_code", "cluster", "year"]).to_csv(OUTPUT, index=False)
print(f"Wrote {len(output_rows)} cluster-year rows to {OUTPUT}")