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
num_samples = 500
num_rhos = 100

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

def valid_isolated_config(g, column):
    nodes_in_cluster = []
    i=0
    for node in g.nodes():
        if g.nodes[node][column] >0:
            nodes_in_cluster.append(node)
        i+=1
    
    # should have as many connected components as there are nonzero entries
    if nx.number_connected_components(g.subgraph(nodes_in_cluster)) == np.count_nonzero([g.nodes[node]["x_pop"] for node in g.nodes]):
        return True
    else:
        return False

def make_random_isolated_config(g, rho):
    # reset populations
    for node in g.nodes():
        g.nodes[node]["x_pop"] = 0
        g.nodes[node]["y_pop"] = g.nodes[node]["TOTPOP"]

    selected = set()
    blocked = set()

    nodes = list(g.nodes())
    random.shuffle(nodes)

    for node in nodes:
        if node in blocked:
            continue

        selected.add(node)
        blocked.add(node)
        blocked.update(g.neighbors(node))

        g.nodes[node]["x_pop"] = g.nodes[node]["TOTPOP"]
        g.nodes[node]["y_pop"] = 0
        current_rho = metrics.property_sum(g, "x_pop") / metrics.property_sum(g, "TOTPOP")
        if current_rho >= rho:
            break

    for node in g.nodes():
        g.nodes[node]["y_pop"] = g.nodes[node]["TOTPOP"] - g.nodes[node]["x_pop"]

    return g, metrics.property_sum(g, "x_pop") / metrics.property_sum(g, "TOTPOP")


g = gerrychain.Graph.from_json("reproduction_data/ia_files/ia_counties_2020.json")

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
plt.savefig("Reproduction/Reproduction_Figures/Iowa/moran_by_rho_isol_iowa.png")

plt.figure(figsize=(10, 10))
plt.scatter(real_rhos, capys, s=0.1, color = "#1560bd")
plt.xlabel(r'$\rho$')
plt.ylabel("Capy")
plt.xlim([0, 0.5])
plt.tight_layout()
plt.savefig("Reproduction/Reproduction_Figures/Iowa/capy_by_rho_isol_iowa.png")

g_, real_rho = make_random_isolated_config(g, RHO)
visualize_iowa(g_)
plt.savefig(f"Reproduction/Reproduction_Figures/Iowa/isol_iowa_visualization_rho={RHO}.png")

    