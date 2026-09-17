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
random.seed(42)

plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm", #setting to latex font
                    "font.size": 28, "savefig.dpi": 300})

"""
This script generates three figures for a uniform Iowa county graph: a capy-vs-rho lineplot, a geographic visualization of county-level rho values, and a standalone diverging colorbar.
Global Parameters:
    RHO: float
        The uniform group fraction used for the geographic visualization and colorbar figures
"""

RHO = 0.3

def colormap(rho, vmin = 0, vmax = 1):
    """
    Builds a diverging colormap and norm centered at rho, running from blue (rho=0) through white (rho=rho) to orange (rho=1).
    Parameters:
        Rho: float
        The rho value at which the colorbar diverges
    """

    diverging_cmap = LinearSegmentedColormap.from_list(
    "rho_diverging",
    ["#2267BC", "#ffffff", "#FFA812"]
    )
    # Norm that maps 0→left, RHO→center (white), 1→right
    norm = TwoSlopeNorm(vmin=vmin, vcenter=rho, vmax=vmax)

    return diverging_cmap, norm

def visualize_iowa(graph, rho ):
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
        math.degrees(math.log(math.tan(math.pi/4 + math.radians(float(graph.nodes[node]["INTPTLAT"]))/2)))
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

    nx.draw_networkx_edges(graph, pos=pos, edge_color="black", width=0.2, alpha=0.5, ax=ax)
    nx.draw_networkx_nodes(graph, pos=pos, node_size=sizes, node_color=node_colors,
                        edgecolors='black', linewidths=0.5, ax=ax)

    ax.set_aspect('equal')
    ax.axis('off')

def make_uniform_iowa(graph, rho):
    """
    Assigns x_pop and y_pop to every node so that each county's group fraction equals rho uniformly.
    Parameters:
        graph: nx.Graph
            County adjacency graph with node attribute TOTPOP
        rho: float
            The uniform group fraction to assign to every node
    """

    for node in graph.nodes():
        graph.nodes[node]["x_pop"] = rho * graph.nodes[node]['TOTPOP']
        graph.nodes[node]["y_pop"]  = (1-rho) * graph.nodes[node]['TOTPOP']
    return graph

def plot_rho_colorbar_diverging(vcenter=RHO, vmin=0, vmax=1, tick_size=10):
    """
    Produces a standalone diverging colorbar figure with a horizontal marker at vcenter labeled with the global rho value.
    Parameters:
        vcenter: float
            The rho value at which the colormap centers (white); also where the dashed marker is drawn
        vmin: float
            Lower bound of the colorbar scale
        vmax: float
            Upper bound of the colorbar scale
        tick_size: int
            Font size for colorbar tick labels
    """

    fig, ax = plt.subplots(figsize=(1.2, 4))
    fig.subplots_adjust(right=0.4)
    cmap, norm = colormap(vcenter, vmin, vmax)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cbar = fig.colorbar(sm, ax=ax, fraction=1.0, pad=0)
    cbar.ax.tick_params(labelsize=tick_size)
    cbar.ax.set_title(r"$\rho_i$", rotation=0, fontsize=tick_size * 3, pad=10)
    cbar.ax.yaxis.set_ticks_position('right')
    cbar.ax.text(1.6, vcenter, fr"$\rho = {vcenter}$", va='center', ha='left',
             fontsize=tick_size, transform=cbar.ax.transData, clip_on=False)
    cbar.ax.axhline(vcenter, color='black', linestyle=':', linewidth=1, clip_on=False)
    
    ax.set_visible(False)


def plot_rho_vs_capy_uniform(graph):
    """
    Plots half_edge capy versus rho for a uniform Iowa graph across 50 evenly spaced rho values between 0.001 and 0.5.
    Parameters:
        graph: nx.Graph
            County adjacency graph with node attribute TOTPOP; copied and modified for each rho value
    """

    num_rhos = 50

    rhos = np.linspace(0.001,0.5, num_rhos)

    # data lists for scores
    capys = np.zeros(num_rhos)

    for i in range(num_rhos):
        g1 = graph.copy()
        g1 = make_uniform_iowa(g1, rhos[i])
        capys[i] = metrics.half_edge(g1, "x_pop", "y_pop")

    plt.scatter(rhos,capys,s=1, color = "#1560bd")
    plt.xlim([0,0.5])
    plt.ylim([0,1])

    plt.tight_layout()

#making plots
graph = gerrychain.Graph.from_json("data/experiment_specific/ia_files/ia_counties_2020.json")

plot_rho_vs_capy_uniform(graph)
plt.savefig("figures/iowa/capy_by_rho_uniform_iowa.png", dpi = 300, bbox_inches="tight")

visualize_iowa(make_uniform_iowa(graph, RHO), RHO)
plt.savefig(f"figures/iowa/uniform_iowa_visualization_rho={RHO}.png", dpi = 300, bbox_inches="tight")

plot_rho_colorbar_diverging(RHO)
plt.savefig(f"figures/iowa/divergent_rho_colorbar_rho={RHO}.png")
