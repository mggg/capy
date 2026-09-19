"""
This script generates scatter plots of capy and Moran's I versus rho for randomly sampled isolated configurations of the Iowa county graph, plus a geographic visualization of one such configuration.
Global Parameters:
    RHO: float
        The target group fraction used for the geographic visualization figure
    num_samples: int
        Number of random isolated configurations to sample at each target rho value
    num_rhos: int
        Number of evenly spaced rho values between 0.01 and 0.5 to sample over
"""

import sys
import os
import pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
IOWA_SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(IOWA_SCRIPTS))
import capy_core.metrics as metrics
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
import random
import pandas as pd
import gerrychain
from iowa_helpers import visualize_iowa, plot_metric_scatterplots
import typer
random.seed(42)

plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm", #setting to latex font
                    "font.size": 28, "savefig.dpi": 300})

RHO = 0.3
num_samples = 500
num_rhos = 100

def main():
    g = gerrychain.Graph.from_json("data/experiment_specific/ia_files/ia_counties_2020.json")

    target_rhos = []
    real_rhos = []
    capys = []
    morans =[]
    rho_grid = np.linspace(0.01, .5, num_rhos)

    for _ in range(num_samples):
        for rho in rho_grid:
            g_, real_rho = make_random_isolated_config(g, rho)

            if not valid_isolated_config(g_, "x_pop"):
                print("invalid configuration")
                continue

            if metrics.property_sum(g_, "x_pop") == 0 or metrics.property_sum(g_, "y_pop") == 0:
                print("0 pop")
                continue

            target_rhos.append(rho)
            real_rhos.append(real_rho)
            capys.append(metrics.half_edge(g_, "y_pop", "x_pop"))
            morans.append(metrics.moran(g_, "x_pop", "TOTPOP")["moran_P"])

    fig_moran, ax_moran, fig_capy, ax_capy = plot_metric_scatterplots(real_rhos, capys, morans)

    fig_moran.savefig("figures/iowa/moran_by_rho_isol_iowa.png", dpi = 300, bbox_inches="tight")
    fig_capy.savefig("figures/iowa/capy_by_rho_isol_iowa.png", dpi = 300, bbox_inches="tight")

    g_, real_rho = make_random_isolated_config(g, RHO)
    fig, ax = visualize_iowa(g_, real_rho)
    base_filename = f"figures/iowa/isol_iowa_visualization_rho={real_rho}"
    filestem = base_filename.replace('.', 'p')
    fig.savefig(f"{filestem}.png", dpi = 300, bbox_inches="tight")
    plt.close(fig)

    pd.DataFrame({
        "target_rho": target_rhos,
        "real_rho": real_rhos,
        "capy": capys,
        "moran": morans,
    }).to_csv(f"stats/iowa_runs/isol_samples_samples={num_samples}_rhos={num_rhos}.csv", index=False)


def valid_isolated_config(graph, column):
    """
    Checks whether the x_pop-carrying nodes in the graph form a valid isolated configuration, where every nonzero node is its own connected component (no two selected nodes are adjacent).
    Parameters:
        graph: nx.Graph
            County adjacency graph with node attribute specified by column
        column: str
            Name of the node attribute to check for nonzero values
    Returns:
        bool
            True if the nonzero nodes form a valid isolated configuration, False otherwise
    """

    nodes_in_cluster = []
    
    for node in graph.nodes():
        if graph.nodes[node][column] >0:
            nodes_in_cluster.append(node)
    
    # should have as many connected components as there are nonzero entries
    subgraph = graph.subgraph(nodes_in_cluster)
    return subgraph.number_of_edges() == 0


def make_random_isolated_config(graph, target_rho):
    """
    Randomly assigns x_pop to a greedy independent set of nodes until the global group fraction reaches rho, then sets y_pop as the remainder for every node.
    Parameters:
        graph: nx.Graph
            County adjacency graph with node attribute TOTPOP; modified in place
        rho: float
            Target global group fraction; assignment stops once this value is reached or exceeded
    Returns:
        graph: nx.Graph
            The modified graph with x_pop and y_pop set on every node
        real_rho: float
    The actual achieved global group fraction. May exceed target_rho if the last selected node overshoots, or fall short of target_rho if the 
    maximal independent set is exhausted before the target is reached.
    """

    # reset populations
    for node in graph.nodes():
        graph.nodes[node]["x_pop"] = 0
        graph.nodes[node]["y_pop"] = graph.nodes[node]["TOTPOP"]

    blocked = set()

    nodes = list(graph.nodes())
    random.shuffle(nodes)

    total_pop =  metrics.property_sum(graph, "TOTPOP")
    x_pop = 0
    for node in nodes:
        if node in blocked:
            continue

        blocked.add(node)
        blocked.update(graph.neighbors(node))

        graph.nodes[node]["x_pop"] = graph.nodes[node]["TOTPOP"]
        x_pop+=graph.nodes[node]["x_pop"]
        graph.nodes[node]["y_pop"] = 0

        current_rho = x_pop / total_pop
        if current_rho >= target_rho:
            break

    for node in graph.nodes():
        graph.nodes[node]["y_pop"] = graph.nodes[node]["TOTPOP"] - graph.nodes[node]["x_pop"]

    return graph, metrics.property_sum(graph, "x_pop") / metrics.property_sum(graph, "TOTPOP")

if __name__ == "__main__":
    typer.run(main)