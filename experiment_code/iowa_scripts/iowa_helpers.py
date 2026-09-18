import sys
import os
import pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
import capy_core.metrics as metrics
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
import random
import math
import gerrychain
from collections import deque
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
random.seed(42)

def colormap(rho, vmin = 0, vmax = 1):
    """
    Builds a diverging colormap and norm centered at rho, running from blue (rho=0) through white (rho=rho) to orange (rho=1).
    Parameters:
        Rho: float
        The rho value at which the colorbar diverges
    """
    if not (vmin < rho < vmax): 
        raise ValueError(f"rho={rho} must be strictly between vmin={vmin} and vmax={vmax}")
    
    diverging_cmap = LinearSegmentedColormap.from_list(
    "rho_diverging",
    ["#2267BC", "#ffffff", "#FFA812"]
    )
    # Norm that maps 0→left, RHO→center (white), 1→right
    norm = TwoSlopeNorm(vmin=vmin, vcenter=rho, vmax=vmax)

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
    fig: matplotlib.figure.Figure
        The figure containing the Iowa graph visualization
    ax: matplotlib.axes.Axes
        The axes on which the graph is drawn
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

    nx.draw_networkx_nodes(graph, pos=pos, node_size=sizes, node_color=node_colors,
                            edgecolors='black', linewidths=0.5, ax=ax)
    nx.draw_networkx_edges(graph, pos=pos, edge_color="black", width=0.2, alpha=0.5, ax=ax)


    ax.set_aspect('equal')
    ax.axis('off')
    return fig, ax

def populate_cluster_random(start_node, graph, target_x_pop):
    """
    Assigns x_pop via random cluster growth expansion from a seed node until the total x_pop reaches target_x_pop, then sets y_pop as the remainder for every node.
    Parameters:
        start_node: int
            The seed node from which random cluster growth expansion begins
        graph: nx.Graph
            County adjacency graph with node attribute TOTPOP; modified in place
        target_x_pop: float
            The total x_pop at which random cluster growth stops adding nodes to the cluster
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

    real_rho = metrics.property_sum(graph, "x_pop")/metrics.property_sum(graph, "TOTPOP")
    
    return graph, real_rho

def plot_rho_colorbar_diverging(vcenter, vmin=0, vmax=1, tick_size=10):
    """
    Produces a standalone diverging colorbar figure with a horizontal marker at vcenter 
    labeled with the global rho value. Currently not used in iowa viz.
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
    return fig, ax