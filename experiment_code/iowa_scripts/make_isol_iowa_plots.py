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
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
random.seed(42)

plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm", #setting to latex font
                    "font.size": 28, "savefig.dpi": 300})

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


g = gerrychain.Graph.from_json("data/experiment_specific/ia_files/ia_counties_2020.json")

real_rhos = []
capys = []
morans =[]

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
        morans.append(metrics.moran(g_, "x_pop", "TOTPOP")["moran_P"])

#setting axis ticks
rho_step = 0.1
xmin = math.floor(min(real_rhos) / rho_step) * rho_step
xmax = math.ceil(max(real_rhos) / rho_step) * rho_step

moran_step = 0.2
moran_ymin = math.floor(min(morans) / moran_step) * moran_step
moran_ymax = math.ceil(max(morans) / moran_step) * moran_step

capy_step = 0.1
capy_ymin = math.floor(min(capys) / capy_step) * capy_step
capy_ymax = math.ceil(max(capys) / capy_step) * capy_step

plt.figure(figsize=(10, 10))
plt.scatter(real_rhos, morans, s=0.1, color = "#1560bd")
plt.xticks(np.arange(xmin, xmax + rho_step/2, rho_step))
plt.xlim(xmin, xmax)
plt.yticks(np.arange(moran_ymin, moran_ymax + moran_step/2, moran_step))
plt.ylim(moran_ymin-0.02, moran_ymax)
plt.savefig("figures/iowa/moran_by_rho_isol_iowa.png", dpi = 300, bbox_inches="tight")

plt.figure(figsize=(10, 10))
plt.scatter(real_rhos, capys, s=0.1, color = "#1560bd")
plt.xticks(np.arange(xmin, xmax + rho_step/2, rho_step))
plt.xlim(xmin, xmax)
plt.yticks(np.arange(capy_ymin, capy_ymax + capy_step/2, capy_step))
plt.ylim(capy_ymin-0.02, capy_ymax)
plt.savefig("figures/iowa/capy_by_rho_isol_iowa.png", dpi = 300, bbox_inches="tight")

g_, real_rho = make_random_isolated_config(g, RHO)
fig, ax = visualize_iowa(g_, real_rho)
base_filename = f"figures/iowa/isol_iowa_visualization_rho={real_rho}"
filestem = base_filename.replace('.', 'p')
fig.savefig(f"{filestem}.png", dpi = 300, bbox_inches="tight")
plt.close(fig)