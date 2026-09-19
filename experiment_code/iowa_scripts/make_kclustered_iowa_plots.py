"""
This script generates scatter plots of capy and Moran's I versus rho for randomly sampled k-cluster configurations of the Iowa county graph, plus a geographic visualization of one such configuration.
Global Parameters:
    RHO: float
        The target group fraction used for the geographic visualization figure
    num_start_nodes: int
        Number of clusters used for the geographic visualization figure
    num_samples: int
        Number of random k-clustered configurations to sample at each rho value
    num_rhos: int
        Number of evenly spaced rho values between 0.001 and 0.5 to sample over
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
import math
import gerrychain
from iowa_helpers import visualize_iowa, populate_cluster_random, plot_metric_scatterplots
import typer
random.seed(42)

plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm", #setting to latex font
                    "font.size": 28, "savefig.dpi": 300})

RHO = 0.3
num_start_nodes = 4
num_samples = 500
num_rhos = 100

def main():
    #loading iowa
    g = gerrychain.Graph.from_json("data/experiment_specific/ia_files/ia_counties_2020.json")

    #visualizing kcluster
    result= generate_kclust_grid(g, RHO, num_start_nodes, max_retries = 5000)
    if result is not None:
        g_, real_rho, num_components = result
        fig, ax = visualize_iowa(g_, real_rho)
        base_filename = f"figures/iowa/multicluster_iowa_visualization_rho={real_rho}_k={num_start_nodes}_numcomponents={num_components}"
        filestem = base_filename.replace('.', 'p')
        fig.savefig(f"{filestem}.png", dpi = 300, bbox_inches="tight")
        plt.close(fig)
    else:
        raise RuntimeError("Graph with more than one cluster could not be generated. Try increasing max_retries, lowering RHO, or lowering num_start_nodes") #something goes horribly wrong

    #sampling kclusters
    real_rhos = []
    capys = []
    morans =[]

    for _ in range(num_samples):
        for rho in np.linspace(.001, .5, num_rhos):
            result = generate_kclust_grid(g, rho, num_start_nodes)
            if result is not None:
                g_, real_rho, num_components = result
                real_rhos.append(real_rho)
                capys.append(metrics.half_edge(g_, "y_pop", "x_pop"))
                morans.append(metrics.moran(g_, "x_pop", "TOTPOP")["moran_P"])

    fig_moran, ax_moran, fig_capy, ax_capy = plot_metric_scatterplots(real_rhos, capys, morans)

    base_filename_moran =f"figures/iowa/moran_by_rho_multicluster_iowa_k={num_start_nodes}"
    filestem_moran = base_filename_moran.replace('.', 'p')
    fig_moran.savefig(f"{filestem_moran}.png", dpi = 300, bbox_inches="tight")

    base_filename_capy =f"figures/iowa/capy_by_rho_multicluster_iowa_k={num_start_nodes}"
    filestem_capy = base_filename_capy.replace('.', 'p')
    fig_capy.savefig(f"{filestem_capy}.png", dpi = 300, bbox_inches="tight")

def generate_kclust_grid(graph, target_rho, num_start_nodes, max_retries = 50):
    """
    Builds a k-cluster configuration by growing num_start_nodes independent random cluster growth clusters, 
    each targeting an equal share of the total x_pop budget, then computes the achieved rho and number of 
    connected components. Clusters from different start nodes can merge into one another but the code only
    returns configurations with at least two unconnected clusters.
    Parameters:
        graph: nx.Graph
            County adjacency graph with node attributes TOTPOP, x_pop, and y_pop; modified in place
        target_rho: float
            Target global group fraction to distribute across num_start_nodes clusters
        num_start_nodes: int
            Number of clusters to grow. Clusters can merge into one another
    Returns:
        G: nx.Graph
            The modified graph with x_pop and y_pop set on every node
        real_rho: float
            The actual achieved global group fraction across all clusters
        components: int
            Number of connected components among the x_pop-carrying nodes
    """
    for _ in range(max_retries):
        for node in graph.nodes():
            graph.nodes[node]["x_pop"] = 0
            graph.nodes[node]["y_pop"] = 0

        target_pop = target_rho * metrics.property_sum(graph, "TOTPOP") / num_start_nodes

        for _ in range(num_start_nodes):
            y_nodes = [node for node in graph.nodes if graph.nodes[node]["x_pop"] == 0]
            if y_nodes == []:
                return None
            seed = random.choice(y_nodes)

            G, cluster_rho = populate_cluster_random(seed, graph, target_pop)

        for node in G.nodes():
            if G.nodes[node]["x_pop"] == 0:
                G.nodes[node]["y_pop"] = graph.nodes[node]["TOTPOP"]
        
        real_rho = (metrics.property_sum(G, "x_pop") / 
                    (metrics.property_sum(G, "x_pop") + 
                    metrics.property_sum(G, "y_pop")))
        
        x_nodes = [
            node for node in G.nodes()
            if G.nodes[node]["x_pop"] > 0
            ]

        H = G.subgraph(x_nodes)

        components = nx.number_connected_components(H)
        if components > 1:
            return G, real_rho, components

    return None

if __name__ == "__main__":
    typer.run(main)