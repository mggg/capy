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
This script generates scatter plots of capy and Moran's I versus rho for randomly sampled k-cluster configurations of the Iowa county graph, plus a geographic visualization of one such configuration.
Global Parameters:
    RHO: float
        The target group fraction used for the geographic visualization figure
    num_seeds: int
        Number of clusters used for the geographic visualization figure
    num_samples: int
        Number of random k-clustered configurations to sample at each rho value
    num_rhos: int
        Number of evenly spaced rho values between 0.001 and 0.5 to sample over
"""

RHO = 0.3
num_seeds = 4
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
    Returns:
        None; draws to the current matplotlib figure
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

def populate_cluster_random(start_node, graph, target_x_pop):
    """
    Assigns x_pop via randomized BFS expansion from a seed node until the total x_pop reaches target_x_pop, then sets y_pop as the remainder for every node.
    Parameters:
        start_node: int
            The seed node from which BFS expansion begins
        graph: nx.Graph
            County adjacency graph with node attribute TOTPOP; modified in place
        target_x_pop: float
            The total x_pop at which BFS stops adding nodes to the cluster
    Returns:
        graph: nx.Graph
            The modified graph with x_pop and y_pop set on every node
        real_rho: float
            The actual achieved global group fraction, which may exceed the target due to discrete node assignments
    """
    
    queue = deque([start_node])

    visited = set()
    x_pop_sum = 0

    while queue and x_pop_sum < target_x_pop:
        queue = list(queue)
        random.shuffle(queue)
        queue = deque(queue)
        node = queue.popleft()

        if node in visited or graph.nodes[node]["x_pop"] > 0:
            visited.add(node)
            continue
        visited.add(node)

        # assign values
        graph.nodes[node]["x_pop"] = graph.nodes[node]["TOTPOP"]
        graph.nodes[node]["y_pop"] = 0

        x_pop_sum += graph.nodes[node]["TOTPOP"]

        # add neighbors (randomized expansion)
        neighbors = list(graph.neighbors(node))
        random.shuffle(neighbors)

        for nbr in neighbors:
            if nbr not in visited:
                queue.append(nbr)


    for node in graph.nodes():
        if graph.nodes[node]["x_pop"] == 0:
            graph.nodes[node]["y_pop"] = graph.nodes[node]["TOTPOP"]

    real_rho = metrics.property_sum(g, "x_pop")/metrics.property_sum(g, "TOTPOP")
    
    return graph, real_rho

def generate_kclust_grid(graph, target_rho, num_seeds, max_retries = 50):
    """
    Builds a k-cluster configuration by growing num_seeds independent BFS clusters, each targeting an equal share of the total x_pop budget, then computes the achieved rho and number of connected components.
    Parameters:
        graph: nx.Graph
            County adjacency graph with node attributes TOTPOP, x_pop, and y_pop; modified in place
        target_rho: float
            Target global group fraction to distribute across num_seeds clusters
        num_seeds: int
            Number of clusters to grow
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

        target_pop = target_rho * metrics.property_sum(graph, "TOTPOP") / num_seeds

        for _ in range(num_seeds):
            y_nodes = [node for node in graph.nodes if graph.nodes[node]["x_pop"] == 0]
            seed = random.choice(y_nodes)

            G, cluster_rho = populate_cluster_random(seed, graph, target_pop)

        for node in G.nodes():
            if G.nodes[node]["x_pop"] == 0:
                G.nodes[node]["y_pop"] = g.nodes[node]["TOTPOP"]
        
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

    return nonde

#loading iowa
g = gerrychain.Graph.from_json("data/experiment_specific/ia_files/ia_counties_2020.json")
for node in g.nodes():
    g.nodes[node]["x_pop"] = 0
    g.nodes[node]["y_pop"] = 0

#visualizing kcluster
g_, real_rho, num_components = generate_kclust_grid(g, RHO, num_seeds)
visualize_iowa(g_, RHO)
plt.savefig(f"figures/iowa/multicluster_iowa_visualization_rho={RHO},k={num_seeds}.png")

real_rhos = []
capys = []
morans =[]

#sampling
for _ in range(num_samples):
    for rho in np.linspace(.001, .5, num_rhos):
        for node in g.nodes():
            g.nodes[node]["x_pop"] = 0
            g.nodes[node]["y_pop"] = 0

        nodes = list(g.nodes())
        seed = random.choice(nodes)
        result = generate_kclust_grid(g, rho, num_seeds)
        if result is not None:
            g_, real_rho, num_components = result
            real_rhos.append(real_rho)
            capys.append(metrics.half_edge(g_, "y_pop", "x_pop"))
            morans.append(metrics.moran(g_, "x_pop", "TOTPOP")["moran_A"])

#plotting scatterplots
plt.figure(figsize=(10, 10))
plt.scatter(real_rhos, morans, s=0.1, color = "#1560bd")
plt.xlabel(r'$\rho$')
plt.ylabel("Moran's I")
plt.xlim([0, 0.5])
plt.tight_layout()
plt.savefig(f"figures/iowa/moran_by_rho_multicluster_iowa_k={num_seeds}.png")

plt.figure(figsize=(10, 10))
plt.scatter(real_rhos, capys, s=0.1, color = "#1560bd")
plt.xlabel(r'$\rho$')
plt.ylabel("Capy")
plt.xlim([0, 0.5])
plt.tight_layout()
plt.savefig(f"figures/iowa/capy_by_rho_multicluster_iowa_k={num_seeds}.png")