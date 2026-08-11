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
    area_total_population = sum(int(graph.nodes[node]["TOTPOP"]) for node in selected_nodes)

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
        "spread": best_objective / area_black_population,
        "center_node_id": best_center,
        "center_gisjoin": graph.nodes[best_center]["GISJOIN"],
        "center_geoid": graph.nodes[best_center].get("GEOID")}


selection_df = pd.read_csv(SELECTIONS, dtype={"area_code": str, "year": int, "cluster": str, "gisjoin": str})


output_rows = []

for (area_code, year, cluster), group in selection_df.groupby(["area_code", "year", "cluster"], sort=True):
    print(f"Calculating metrics for area_code {area_code}, year {year}, cluster {cluster}.")
    matches = sorted(
            (GRAPH_DIR / str(year)).glob(f"tracts_in_max_city_{area_code}_{year}_*_connected.json"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one city graph for area_code {area_code} in {year}, but found {len(matches)}.")
    graph = gerrychain.Graph.from_json(matches[0])

    metrics = calculate_cluster_spread(graph, gisjoins=group["gisjoin"].tolist())

    output_rows.append({"area_code": area_code, "year": year, "cluster": cluster, **metrics})

pd.DataFrame(output_rows).sort_values(["area_code", "cluster", "year"]).to_csv(OUTPUT, index=False)
print(f"Wrote {len(output_rows)} cluster-year rows to {OUTPUT}")