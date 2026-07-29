# Calculate metrics for one (for now manually selected) cluster-year area and save
from pathlib import Path
import gerrychain
import networkx as nx
import pandas as pd

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
# SELECTIONS = EXPERIMENT_DIR / "data" / "manual_cluster_tracts.csv"
SELECTIONS = EXPERIMENT_DIR / "data" / "auto_cluster_tracts.csv"
GRAPH_DIR = EXPERIMENT_DIR.parent.parent / "data" / "processed" / "dual_graphs"
OUTPUT = EXPERIMENT_DIR / "data" / "cluster_metrics.csv"
OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"


def calculate_cluster_metrics(graph, gisjoins): #core_gisjoins):
    """
    Calculates metrics for one supplied cluster-year area and core cluster.
    Parameters:
    ----------
    graph: gerrychain.Graph
        The dual graph for the CBSA and year of interest.
    gisjoins: list of str
        The GISJOINs of the tracts in the catchment.
    Returns
    -------
    dict
        A dictionary containing the calculated metrics for the catchment area and core cluster.
    """
    # Translate the supplied catchment area and core GISJOINs to graph node IDs, {GISJOIN: node_id}
    nodes_by_gisjoin = {str(attrs["GISJOIN"]): node for node, attrs in graph.nodes(data=True)}
    missing = [g for g in gisjoins if g not in nodes_by_gisjoin]
    if missing:
        print(f"  Warning: skipping {len(missing)} GISJOIN(s) not found in graph: {missing}")
    selected_nodes = [nodes_by_gisjoin[g] for g in gisjoins if g in nodes_by_gisjoin]
    if not selected_nodes:
        raise ValueError("No GISJOINs matched the graph — cluster-year has no valid tracts.")

    area_black_population = sum(int(graph.nodes[node]["BLACK"]) for node in selected_nodes)
    area_total_population = sum(int(graph.nodes[node]["TOTPOP"]) for node in selected_nodes)

    # Test every tract and pick the graph centroid. Centroid minimizes the sum of distances to all other tracts in the catchment area, weighted by Black population.
    best_center = None
    best_objective = None
    for candidate in selected_nodes:
        distances = nx.single_source_shortest_path_length(graph, candidate)
        objective = sum(
            int(graph.nodes[node]["BLACK"]) * distances[node] for node in selected_nodes)
        # The candidate tract itself contributes zero because its distance to itself is zero
        # tie_break = str(graph.nodes[candidate]["GISJOIN"])
        if best_objective is None or objective < best_objective: # (objective, tie_break) < (best_objective, str(graph.nodes[best_center]["GISJOIN"])):
            best_center = candidate
            best_objective = objective

    selected_subgraph = graph.subgraph(selected_nodes)
    return {
        "tract_count": len(selected_nodes),
        "component_count": nx.number_connected_components(selected_subgraph), # should be 1
        "area_black_population": area_black_population,
        "area_total_population": area_total_population,
        "area_black_share": area_black_population / area_total_population,
        "spread": best_objective / area_black_population,
        "center_node_id": best_center,
        "center_gisjoin": graph.nodes[best_center]["GISJOIN"],
        "center_geoid": graph.nodes[best_center].get("GEOID")}


# SKIP = {("37980", 1980, "south")}

output_rows = []
selection_df = pd.read_csv(SELECTIONS, dtype={"cbsa": str, "year": int, "cluster": str, "gisjoin": str}) #, "is_core": str})

for (cbsa, year, cluster), group in selection_df.groupby(["cbsa", "year", "cluster"], sort=True):
    # if (cbsa, year, cluster) in SKIP:
    #     print(f"Skipping CBSA {cbsa}, year {year}, cluster {cluster} (bad CSV).")
    #     continue
    print(f"Calculating metrics for CBSA {cbsa}, year {year}, cluster {cluster}.")
    # find and read the dual graph for this CBSA and year:
    matches = sorted(
            (GRAPH_DIR / str(year)).glob(
                f"tracts_in_cbsa_{cbsa}_{year}_*_orig.json"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one connected graph for CBSA {cbsa} in {year}, but found {len(matches)}.")
    graph = gerrychain.Graph.from_json(matches[0])

    # Determine which tracts in the catchment area are part of the core cluster
    # is_core = group["is_core"].astype(str).str.lower().eq("true")
    # Threshold used to define the catchment area is the same for all tracts, so just take the 1st value
    # catchment_threshold = group["catchment_threshold"].iloc[0]
    # Core tracts IDs:
    # core_gisjoins = group.loc[is_core, "gisjoin"].tolist()

    metrics = calculate_cluster_metrics(graph, group["gisjoin"].tolist()) #, core_gisjoins)
    
    output_rows.append({"cbsa": cbsa,
                        "year": year,
                        "cluster": cluster,
                        # "catchment_threshold": catchment_threshold,
                        **metrics})


    OUTPUTS_DIR.mkdir(exist_ok=True)
    pd.DataFrame(output_rows).sort_values(["cbsa", "cluster", "year"]).to_csv(OUTPUT, index=False)
    print(f"Wrote {len(output_rows)} cluster-year rows to {OUTPUT}")