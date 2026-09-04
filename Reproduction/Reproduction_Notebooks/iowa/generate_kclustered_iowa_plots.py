import sys, os
import os
os.chdir("/Users/samstephenson/Downloads/capy-bara")
sys.path.insert(0, "/Users/samstephenson/Downloads/capy-bara")

import pipeline.metrics as metrics
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

RHO = 0.3
K = 10
num_samples = 500
num_rhos = 100


def populate_cluster_random(start_node, G, tot_x_pop):
    
    queue = deque([start_node])

    visited = set()
    x_pop_sum = 0

    while queue and x_pop_sum < tot_x_pop:
        queue = list(queue)
        random.shuffle(queue)
        queue = deque(queue)
        node = queue.popleft()

        if node in visited or G.nodes[node]["x_pop"] > 0:
            visited.add(node)
            continue
        visited.add(node)

        # assign values
        G.nodes[node]["x_pop"] = G.nodes[node]["TOTPOP"]
        G.nodes[node]["y_pop"] = 0

        x_pop_sum += G.nodes[node]["TOTPOP"]

        # add neighbors (randomized expansion)
        neighbors = list(G.neighbors(node))
        random.shuffle(neighbors)

        for nbr in neighbors:
            if nbr not in visited:
                queue.append(nbr)


    for node in G.nodes():
        if G.nodes[node]["x_pop"] == 0:
            G.nodes[node]["y_pop"] = G.nodes[node]["TOTPOP"]

    real_rho = metrics.property_sum(g, "x_pop")/metrics.property_sum(g, "TOTPOP")
    
    return G, real_rho

def generate_kclust_grid(G, rho, k):

    target_pop = rho * metrics.property_sum(G, "TOTPOP") / k 

    # remove seeds = random.sample(...) above the loop

    for _ in range(k):
        y_nodes = [node for node in G.nodes if G.nodes[node]["x_pop"] == 0]
        seed = random.choice(y_nodes)

        G, cluster_rho = populate_cluster_random(seed, G, target_pop)

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

    return G, real_rho, components

def visualize_iowa(g):
    pos = {
    node: (
        float(g.nodes[node]["INTPTLON"]),
        math.degrees(math.log(math.tan(math.pi/4 + math.radians(float(g.nodes[node]["INTPTLAT"]))/2)))
    )
    for node in g.nodes()
    }

    pop = {
        node: g.nodes[node]["TOTPOP"]
        for node in g.nodes()
    }

    sizes = [pop[n] / 500 for n in g.nodes]  # adjust scaling factor
    fig, ax = plt.subplots(figsize=(10, 10))

    node_rhos = [g.nodes[node]["x_pop"] / g.nodes[node]["TOTPOP"] for node in g.nodes()]

    nx.draw_networkx_edges(g, pos=pos, edge_color="black", width=0.2, alpha=0.5, ax=ax)
    nx.draw_networkx_nodes(g, pos=pos, node_size=sizes, node_color=node_rhos,
                            cmap=plt.cm.Blues, vmin=0, vmax=1,
                            edgecolors='black', linewidths=0.5, ax=ax)

    ax.set_aspect('equal')
    ax.axis('off')

g = gerrychain.Graph.from_json("reproduction_data/ia_files/ia_counties_2020.json")
for node in g.nodes():
    g.nodes[node]["x_pop"] = 0
    g.nodes[node]["y_pop"] = 0

g_, real_rho, num_components = generate_kclust_grid(g, RHO, k=K)
visualize_iowa(g_)
plt.savefig(f"Reproduction/Reproduction_Figures/Iowa/multicluster_iowa_visualization_rho={RHO},k={K}.png")

real_rhos = []
capys = []
morans =[]


for _ in range(num_samples):
    for rho in np.linspace(.001, .5, num_rhos):
        for node in g.nodes():
            g.nodes[node]["x_pop"] = 0
            g.nodes[node]["y_pop"] = 0

        nodes = list(g.nodes())
        seed = random.choice(nodes)
        g_, real_rho, num_components = generate_kclust_grid(g, rho, k=10)
        real_rhos.append(real_rho)
        capys.append(metrics.half_edge(g_, "y_pop", "x_pop"))
        morans.append(metrics.moran(g_, "x_pop", "TOTPOP")["moran_A"])

plt.figure(figsize=(10, 10))
plt.scatter(real_rhos, morans, s=0.1, color = "#1560bd")
plt.xlabel(r'$\rho$')
plt.ylabel("Moran's I")
plt.xlim([0, 0.5])
plt.tight_layout()
plt.savefig(f"Reproduction/Reproduction_Figures/Iowa/moran_by_rho_multicluster_iowa_k={K}.png")

plt.figure(figsize=(10, 10))
plt.scatter(real_rhos, capys, s=0.1, color = "#1560bd")
plt.xlabel(r'$\rho$')
plt.ylabel("Capy")
plt.xlim([0, 0.5])
plt.tight_layout()
plt.savefig(f"Reproduction/Reproduction_Figures/Iowa/capy_by_rho_multicluster_iowa_k={K}.png")
