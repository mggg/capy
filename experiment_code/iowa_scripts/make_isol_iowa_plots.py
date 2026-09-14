import sys, os
import os
os.chdir("/Users/samstephenson/Downloads/capy-bara")
sys.path.insert(0, "/Users/samstephenson/Downloads/capy-bara")

import capy_core.metrics as metrics
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import geopandas as gpd
import gerrychain.grid
import random
from collections import deque
import warnings
import tqdm
from collections import deque, defaultdict
import math
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

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

RHO = 0.3
num_samples = 500
num_rhos = 100

def colormap(rho):
    """
    Builds a diverging colormap and norm centered at rho, running from blue (rho=0) through white (rho=rho) to orange (rho=1).
    Parameters:
        rho: float
            The group fraction value at which the colormap centers (white)
    Returns:
        diverging_cmap: LinearSegmentedColormap
            The blue-white-orange diverging colormap
        norm: TwoSlopeNorm
            Normalizer mapping [0, rho, 1] to the colormap endpoints and center
    """


    diverging_cmap = LinearSegmentedColormap.from_list(
    "rho_diverging",
    ["#2267BC", "#ffffff", "#FFA812"]
    )
    # Norm that maps 0→left, RHO→center (white), 1→right
    norm = TwoSlopeNorm(vmin=0, vcenter=rho, vmax=1)

    return diverging_cmap, norm


def visualize_iowa(graph, rho):
    """
    Draws the Iowa county adjacency graph with nodes positioned by Mercator-projected lat/lon, colored by each county's local rho value and sized by total population.
    Parameters:
        graph: nx.Graph
            County adjacency graph with node attributes INTPTLON, INTPTLAT, TOTPOP, and x_pop
        rho: float
            The global rho value used to center the diverging colormap
    """

    pos = {
    node: (
        float(graph.nodes[node]["INTPTLON"]),
        math.degrees(math.log(math.tan(math.pi/4 + math.radians(float(g.nodes[node]["INTPTLAT"]))/2)))
    )
    for node in graph.nodes()
    }

    pop = {
        node: graph.nodes[node]["TOTPOP"]
        for node in graph.nodes()
    }

    sizes = [pop[n] / 500 for n in graph.nodes]  # adjust scaling factor
    fig, ax = plt.subplots(figsize=(10, 10))

    node_rhos = [graph.nodes[node]["x_pop"] / graph.nodes[node]["TOTPOP"] for node in graph.nodes()]

    cmap, norm = colormap(rho)
    node_colors = [cmap(norm(r)) for r in node_rhos]

    nx.draw_networkx_nodes(graph, pos=pos, node_size=sizes, node_color=node_colors,
                            edgecolors='black', linewidths=0.5, ax=ax)
    nx.draw_networkx_edges(graph, pos=pos, edge_color="black", width=0.2, alpha=0.5, ax=ax)


    ax.set_aspect('equal')
    ax.axis('off')

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
    i=0
    for node in graph.nodes():
        if graph.nodes[node][column] >0:
            nodes_in_cluster.append(node)
        i+=1
    
    # should have as many connected components as there are nonzero entries
    if nx.number_connected_components(g.subgraph(nodes_in_cluster)) == np.count_nonzero([graph.nodes[node]["x_pop"] for node in graph.nodes]):
        return True
    else:
        return False

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
            The actual achieved global group fraction, which may exceed rho due to discrete node assignments
    """

    # reset populations
    for node in graph.nodes():
        graph.nodes[node]["x_pop"] = 0
        graph.nodes[node]["y_pop"] = graph.nodes[node]["TOTPOP"]

    selected = set()
    blocked = set()

    nodes = list(graph.nodes())
    random.shuffle(nodes)

    for node in nodes:
        if node in blocked:
            continue

        selected.add(node)
        blocked.add(node)
        blocked.update(g.neighbors(node))

        graph.nodes[node]["x_pop"] = graph.nodes[node]["TOTPOP"]
        graph.nodes[node]["y_pop"] = 0
        current_rho = metrics.property_sum(graph, "x_pop") / metrics.property_sum(graph, "TOTPOP")
        if current_rho >= target_rho:
            break

    for node in graph.nodes():
        g.nodes[node]["y_pop"] = g.nodes[node]["TOTPOP"] - g.nodes[node]["x_pop"]

    return g, metrics.property_sum(graph, "x_pop") / metrics.property_sum(graph, "TOTPOP")


g = gerrychain.Graph.from_json("data/experiment_specific/ia_files/ia_counties_2020.json")

total_pop = metrics.property_sum(g, "TOTPOP")

real_rhos = []
capys = []
morans =[]



num_samples = 500
num_rhos = 100
for _ in range(num_samples):
    for rho in np.linspace(0.01, .5, num_rhos):
        g_, real_rho = make_random_isolated_config(g, rho)

        if not valid_isolated_config(g_, "x_pop"):
            print("invalid configuration")
            continue

        if metrics.property_sum(g_, "x_pop") == 0 or metrics.property_sum(g_, "y_pop") == 0:
            print("0 pop")
            continue

        real_rhos.append(real_rho)
        capys.append(metrics.half_edge(g_, "y_pop", "x_pop"))
        morans.append(metrics.moran(g_, "x_pop", "TOTPOP")["moran_A"])


plt.figure(figsize=(10, 10))
plt.scatter(real_rhos, morans, s=0.1, color = "#1560bd")
plt.xlabel(r'$\rho$')
plt.ylabel("Moran's I")
plt.xlim([0, 0.5])
plt.tight_layout()
plt.savefig("figures/iowa/moran_by_rho_isol_iowa.png")

plt.figure(figsize=(10, 10))
plt.scatter(real_rhos, capys, s=0.1, color = "#1560bd")
plt.xlabel(r'$\rho$')
plt.ylabel("Capy")
plt.xlim([0, 0.5])
plt.tight_layout()
plt.savefig("figures/iowa/capy_by_rho_isol_iowa.png")

g_, real_rho = make_random_isolated_config(g, RHO)
visualize_iowa(g_, RHO)
plt.savefig(f"figures/iowa/isol_iowa_visualization_rho={RHO}.png")

    