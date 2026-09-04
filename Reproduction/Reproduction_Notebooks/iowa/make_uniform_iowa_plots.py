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
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

RHO = 0.3

def colormap(rho):
    cmap = LinearSegmentedColormap.from_list(
        "rho_diverging",
        [(0.0, "#2267BC"), (rho, "#ffffff"), (1.0, "#FFA812")]
    )
    norm = plt.Normalize(vmin=0, vmax=1)
    return cmap, norm

def visualize_iowa(g, rho ):
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

    cmap, norm = colormap(rho)
    colors = cmap(norm(node_rhos))

    nx.draw_networkx_nodes(g, pos=pos, node_size=sizes, node_color=colors,
                        edgecolors='black', linewidths=0.5, ax=ax)
    nx.draw_networkx_edges(g, pos=pos, edge_color="black", width=0.2, alpha=0.5, ax=ax)

    ax.set_aspect('equal')
    ax.axis('off')

def make_uniform_iowa(g, rho):
    for node in g.nodes():
        g.nodes[node]["x_pop"] = rho * g.nodes[node]['TOTPOP']
        g.nodes[node]["y_pop"]  = (1-rho) * g.nodes[node]['TOTPOP']
    return g

def plot_rho_colorbar_diverging(vcenter=RHO, vmin=0, vmax=1, tick_size=10):
    fig, ax = plt.subplots(figsize=(0.5, 4))
    cmap, norm = colormap(vcenter)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cbar = fig.colorbar(sm, cax=ax)
    cbar.ax.tick_params(labelsize=tick_size)
    cbar.ax.set_title(r"$\rho_i$", rotation=0, fontsize=tick_size * 3, pad=10)

    cbar.ax.yaxis.set_ticks_position('right')
    cbar.ax.text(1.6, vcenter, fr"$\rho = {RHO}$", va='center', ha='left',
             fontsize=tick_size, transform=cbar.ax.transData, clip_on=False)
    cbar.ax.plot([0, 1.5], [vcenter, vcenter],
             color='black', linestyle=':', linewidth=1,
             clip_on=False, transform=cbar.ax.get_yaxis_transform())



    plt.tight_layout()

def plot_rho_vs_capy_uniform(g):
    num_rhos = 50

    rhos = np.linspace(0.001,0.5, num_rhos)

    # data lists for scores
    hcaps = np.zeros(num_rhos)
    ecaps = np.zeros(num_rhos)

    for i in range(num_rhos):
        g1 = g.copy()
        g1 = make_uniform_iowa(g1, rhos[i])
        hcaps[i] = metrics.half_edge(g1, "x_pop", "y_pop")
        ecaps[i] = metrics.edge(g1, "x_pop", "y_pop")

    plt.scatter(rhos,hcaps,s=1, color = "#1560bd")
    plt.xlabel(u"\u03C1")
    plt.xlim([0,0.5])
    plt.ylim([0,1])
    plt.ylabel('Capy')

    plt.tight_layout()


g = gerrychain.Graph.from_json("reproduction_data/ia_files/ia_counties_2020.json")

plot_rho_vs_capy_uniform(g)
plt.savefig("Reproduction/Reproduction_Figures/Iowa/capy_by_rho_uniform_iowa.png")

visualize_iowa(make_uniform_iowa(g, RHO), RHO)
plt.savefig(f"Reproduction/Reproduction_Figures/Iowa/uniform_iowa_visualization_rho={RHO}.png")

plot_rho_colorbar_diverging(vcenter = RHO)
plt.savefig(f"Reproduction/Reproduction_Figures/Iowa/rho_colorbar_rho={RHO}.png", bbox_inches='tight')
