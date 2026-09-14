import sys, os
sys.path.insert(0, os.path.abspath("../.."))   
sys.path.insert(0, os.path.abspath("."))           
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import capy_core.metrics as metrics
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import gerrychain.grid
import random
from collections import deque
import warnings
import seaborn as sns
from grid_figs_helpers import generate_ch_grid, generate_const_grid, generate_clust_grid, generate_isol_grid, generate_kclust_grid, draw_grid_as_checkerboard
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
random.seed(53)

"""
This scripts simulates diffusion from a core on grid graphs. Diffusion works according to the following algorithm:

1. initialize by taking some graph and selecting all nodes with rho greater than or equal to some threshold as the core
2. select all core nodes and all neighbours of the core nodes to be the "new_core". Find the total sum of x and y population in the new core and set the new core to have this population uniformly distributed across it.
3. repeat step 2 with new core as the core. End when you reach a uniform graph

The scripts simulates the diffusion process on five initially configured grids. For each grid it both plots a step by step visualization of 1) the polygonal grid at each step of diffusion and 2) lineplots of Moran's I,
Capy, and Dissimilarity by step of diffusion.

Global Parameters:
    node_pop: int
        the population at each node
"""

node_pop = 1

def diffuse(graph, threshold):
    """
    This function simulates the diffusion process on a single graph.

    parameters:
        G: gerrychain.grid.Grid
            the graph the diffusion process happens to
        threshold: float
            the threshold. All nodes with rho greater than or equal to this threshold form the initial core
    returns
        graphs: list(nx.graph)
            a list of nx.graph objects such that graphs[i] stores the graph after diffusion step i
            (with the original graph being stored at graphs[0])
        core_rhos: list(float)
            a list of rhos indexed by step (starting at step 0). rhos[i] is the rho of all nodes in the core region after step i.
    """
    for node in graph.graph.nodes():
        graph.graph.nodes[node]["tot_pop"] = graph.graph.nodes[node]["x_pop"] + graph.graph.nodes[node]["y_pop"]
        graph.graph.nodes[node]["rho"] = graph.graph.nodes[node]["x_pop"] / graph.graph.nodes[node]["tot_pop"]
    graphs = [G.graph.copy()]
    
    core_nodes = [n for n in G.graph.nodes() if G.graph.nodes[n]["rho"] > threshold]
    core_nodes = set(core_nodes)
    core_x = sum(G.graph.nodes[n]["x_pop"] for n in core_nodes)
    core_y = sum(G.graph.nodes[n]["y_pop"] for n in core_nodes)
    core_rho = core_x / (core_x + core_y)
    core_rhos = [core_rho]
    if not core_nodes:
        raise ValueError("No nodes exceed the threshold.")
    if nx.number_connected_components(graph.graph) != 1:
        raise ValueError("The graph must be connected for diffusion to occur.")
    while core_nodes != set(graph.graph.nodes()):
        new_nodes = {nbr for node in core_nodes for nbr in graph.graph.neighbors(node) if nbr not in core_nodes}
        core_nodes |= new_nodes
        core_x = sum(graph.graph.nodes[n]["x_pop"] for n in core_nodes)
        core_y = sum(graph.graph.nodes[n]["y_pop"] for n in core_nodes)
        core_rho = core_x / (core_x + core_y)
        core_rhos.append(core_rho)

        for node in core_nodes:
            graph.graph.nodes[node]["x_pop"] = core_rho * node_pop
            graph.graph.nodes[node]["y_pop"] = (1 - core_rho) * node_pop
        for node in G.graph.nodes():
            graph.graph.nodes[node]["tot_pop"] = graph.graph.nodes[node]["x_pop"] + graph.graph.nodes[node]["y_pop"]
            graph.graph.nodes[node]["rho"] = graph.graph.nodes[node]["x_pop"] / graph.graph.nodes[node]["tot_pop"]
        graphs.append(graph.graph.copy())
    return graphs, core_rhos

def visualize_diffusion_step(graph, step):
    """
    Plots the polygonal grid of step i of the diffusion process

    Parameters
    ----------
    graphs : list of nx.Graph
        Sequence of graph snapshots from diffuse(), one per step.
    rhos : list of float
        Fraction of x_pop in the core region after each step,
        parallel to graphs.
    """
    nodelist = list(G.nodes())
    checker_cols = [n[0] for n in nodelist]
    checker_rows = [n[1] for n in nodelist]
    width  = max(checker_cols) + 1
    height = max(checker_rows) + 1
    grid = np.zeros((height, width))
    for node in nodelist:
        grid[node[1], node[0]] = G.nodes[node]["rho"]


    ax.imshow(grid, cmap=diverging_cmap, norm=norm, origin="lower", interpolation="nearest")

    ax.set_aspect('equal')

    for x in range(width + 1):
        ax.axvline(x - 0.5, color='black', linewidth=0.5)
    for y in range(height + 1):
        ax.axhline(y - 0.5, color='black', linewidth=0.5)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.5)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)


def visualize_diffusion(graphs, core_rhos):
    """
    Plots the polygonal grid of each step of the diffusion process

    Parameters
    ----------
    graphs : list of nx.Graph
        Sequence of graph snapshots from diffuse(), one per step.
    rhos : list of float
        Fraction of x_pop in the core region after each step,
        parallel to graphs.
    """

    rows = len(graphs) // 5
    if len(graphs) % 5 != 0:
        rows += 1
    fig, axes = plt.subplots(rows, 5, figsize=(15, 3 *rows), squeeze = False, constrained_layout=True)
    fig.subplots_adjust(hspace=0.4)
    diverging_cmap = LinearSegmentedColormap.from_list("rho_diverging", ["#2267BC", "#ffffff", "#FFA812"])
    norm = TwoSlopeNorm(vmin=0, vcenter=core_rhos[-1], vmax=1) #diverges at the global rho, here thats rhos[-1] because the rho of the core region is 0 at the end of the process (this might be fragile)

    for i, G in enumerate(graphs):
        ax = axes[i // 5, i % 5]

        nodelist = list(G.nodes())
        checker_cols = [n[0] for n in nodelist]
        checker_rows = [n[1] for n in nodelist]
        width  = max(checker_cols) + 1
        height = max(checker_rows) + 1
        grid = np.zeros((height, width))
        for node in nodelist:
            grid[node[1], node[0]] = G.nodes[node]["rho"]


        ax.imshow(grid, cmap=diverging_cmap, norm=norm, origin="lower", interpolation="nearest")

        ax.set_aspect('equal')
  
        for x in range(width + 1):
            ax.axvline(x - 0.5, color='black', linewidth=0.5)
        for y in range(height + 1):
            ax.axhline(y - 0.5, color='black', linewidth=0.5)

        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(0.5)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        ax.set_title(f"$\\mathbf{{Step\\ {i}}}$\n$\\rho$ of core region after step {i} ={core_rhos[i]:.2f}")
    for j in range(len(graphs), rows * 5):
        axes[j // 5, j % 5].axis("off")

def plot_metrics_over_diffusion(graphs):
    """
    Plots a lineplots of Capy (half_edge), Moran's I, and Dissimilarity by diffusion step.

    Parameters
    ----------
    graphs : list of nx.Graph
        Sequence of graph snapshots from diffuse(), one per step.
    """

    capys = [metrics.half_edge(G, "x_pop", "y_pop") for G in graphs]
    morans = []
    for G in graphs:
        try:
            morans.append(metrics.moran(G, "x_pop", "tot_pop")["moran_P"])
        except ZeroDivisionError:
            morans.append(np.nan)
    dissimilarities = [metrics.dissimilarity(G, "x_pop", "y_pop", 1) for G in graphs]
    steps = list(range(len(graphs)))

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(steps, capys, marker="o", label="Capy", color="#69359c")
    ax.plot(steps[:-1], morans[:-1], marker="o", label="Moran's I (P Matrix)", color="#ffbf00")
    ax.plot(steps, dissimilarities, marker="o", label="Dissimilarity", color="#d11a42")
    ax.legend(loc='lower left')

    ax.set_ylim(-0.1, 1)
    ax.set_ylabel("Metric Value")
    ax.set_xlabel("Steps")

    plt.tight_layout()

def plot_metrics_over_diffusion_two_axes(graphs):
    """
    Plots Capy (half_edge) and Moran's I by diffusion step on two separate y-axes.

    Capy is plotted on the right y-axis (range 0.4–1, purple) and Moran's I on the
    left y-axis (range −0.2–1, yellow). A shared dashed reference line marks the
    no-spatial-structure baseline (Capy = 0.5, Moran's I = 0). Dissimilarity is
    excluded because its scale overlaps poorly with the two-axis layout.

    Parameters
    ----------
    graphs : list of nx.Graph
        Sequence of graph snapshots from diffuse(), one per step. The last step
        is omitted from the Moran's I line because a fully uniform graph produces
        a ZeroDivisionError that is replaced with NaN.
    """
    capys = [metrics.half_edge(G, "x_pop", "y_pop") for G in graphs]
    morans = []
    for G in graphs:
        try:
            morans.append(metrics.moran(G, "x_pop", "tot_pop")["moran_P"])
        except ZeroDivisionError:
            morans.append(np.nan)
    steps = list(range(len(graphs)))

    cfig, ax_moran = plt.subplots(figsize=(8, 5))
    ax_capy = ax_moran.twinx()

    ax_moran.plot(steps[:-1], morans[:-1], marker="o", label="Moran's I", color="#d11a42")
    ax_capy.plot(steps, capys, marker="o", label="Capy", color="#1560bd")

    ax_moran.set_ylim(-.2, 1)#scaled so that substantively both metrics range from slightly hyperintegrated to fully segregated
    ax_capy.set_ylim(0.4, 1)

    ax_moran.tick_params(axis="y", labelcolor="#d11a42")
    ax_capy.tick_params(axis="y", labelcolor="#1560bd")
    ax_capy.axhline(0.5, color="black", linestyle="--", linewidth=1, label="Capy = 0.5, Moran's I = 0")

    lines_m, labels_m = ax_moran.get_legend_handles_labels()
    lines_c, labels_c = ax_capy.get_legend_handles_labels()
    ax_moran.legend(lines_m + lines_c, labels_m + labels_c, loc="lower left")

    ax_moran.legend().remove()

    legend_fig, legend_ax = plt.subplots()
    legend_ax.axis("off")
    legend_ax.legend(lines_m + lines_c, labels_m + labels_c, loc="center",
                    fontsize=8, handlelength=1.5, handleheight=.75,
                    handletextpad=0.4, borderpad=0.4)
    legend_fig.set_size_inches(3, 1)

    plt.tight_layout()
    return cfig, legend_fig

def generate_2_corner_grid(num_columns, num_rows, node_pop):
    """
    Generate a gerrychain Grid with a 2x2 block of x_pop nodes in the (0,0) corner.

    Parameters
    ----------
    n, m : int
        Grid dimensions.
    M : int or float
        Population per node.

    Returns
    -------
    gerrychain.grid.Grid
    """

    G = gerrychain.grid.Grid((num_columns, num_rows))
    for node in G.graph.nodes:
        G.graph.nodes[node]["x"] = node[0]
        G.graph.nodes[node]["y"] = node[1]
        G.graph.nodes[node]["sum"] = node[0] + node[1]
    for i in range(2):
        for j in range(2):
            G.graph.nodes[(i,j)]["x_pop"] = node_pop
            G.graph.nodes[(i,j)]["y_pop"] = 0
    for node in G.graph.nodes():
        if "x_pop" not in G.graph.nodes[node]:
            G.graph.nodes[node]["x_pop"] = 0
            G.graph.nodes[node]["y_pop"] = node_pop
    return G

def generate_center_grid(num_columns, num_rows, node_pop):
    """
    Generate a gerrychain Grid with a 2x2 block of x_pop nodes at the center.

    Parameters
    ----------
    n, m : int
        Grid dimensions.
    M : int or float
        Population per node.

    Returns
    -------
    gerrychain.grid.Grid
    """
    G = gerrychain.grid.Grid((num_columns, num_rows))
    for node in G.graph.nodes:
        G.graph.nodes[node]["x"] = node[0]
        G.graph.nodes[node]["y"] = node[1]
        G.graph.nodes[node]["sum"] = node[0] + node[1]

    cx, cy = num_columns // 2, num_rows // 2
    x_pop_offsets = {
        (dc, dr)
        for dc in range(-2, 2)
        for dr in range(-2, 2)
    }
    for dc, dr in x_pop_offsets:
        G.graph.nodes[(cx + dc, cy + dr)]["x_pop"] = node_pop
        G.graph.nodes[(cx + dc, cy + dr)]["y_pop"] = 0


    for node in G.graph.nodes():
        if "x_pop" not in G.graph.nodes[node]:
            G.graph.nodes[node]["x_pop"] = 0
            G.graph.nodes[node]["y_pop"] = node_pop
    return G

def generate_outer_grid(num_columns, num_rows, node_pop):
    """
    Generate a gerrychain Grid where x_pop occupies the outer ring of nodes.

    Parameters
    ----------
    n, m : int
        Grid dimensions.
    M : int or float
        Population per node.

    Returns
    -------
    gerrychain.grid.Grid
    """

    G = gerrychain.grid.Grid((num_columns, num_rows))
    for node in G.graph.nodes:
        G.graph.nodes[node]["x"] = node[0]
        G.graph.nodes[node]["y"] = node[1]
        G.graph.nodes[node]["sum"] = node[0] + node[1]
    for i in range(num_columns):
        G.graph.nodes[(i, 0)]["x_pop"] = node_pop
        G.graph.nodes[(i, 0)]["y_pop"] = 0
        G.graph.nodes[(i, num_rows - 1)]["x_pop"] = node_pop
        G.graph.nodes[(i, num_rows - 1)]["y_pop"] = 0
    for j in range(num_rows):
        G.graph.nodes[(0, j)]["x_pop"] = node_pop
        G.graph.nodes[(0, j)]["y_pop"] = 0
        G.graph.nodes[(num_columns - 1, j)]["x_pop"] = node_pop
        G.graph.nodes[(num_columns - 1, j)]["y_pop"] = 0
    for node in G.graph.nodes():
        if "x_pop" not in G.graph.nodes[node]:
            G.graph.nodes[node]["x_pop"] = 0
            G.graph.nodes[node]["y_pop"] = node_pop
    return G

###below code creates the plots
#2clusters-random
#G = generate_kclust_grid(10, 10, 0.3, node_pop, 3, method="random")[0]
#graphs, rhos = diffuse(G, threshold=0.3)
#visualize_diffusion(graphs, rhos)
#plt.savefig("figures/idealized_grids_diffusion/diffusion_random_2cluster_rho=p3_graph_visualization.png", dpi=300)
#plot_metrics_over_diffusion_two_axes(graphs)
#plt.savefig("figures/idealized_grids_diffusion/diffusion_random_2cluster_rho=p3_metrics_visualization.png", dpi=300)

#1cluster-random
#G = generate_clust_grid(10, 10, 0.3, node_pop, method="random")
#graphs, rhos = diffuse(G, threshold=0.3)
#visualize_diffusion(graphs, rhos)
#plt.savefig("figures/idealized_grids_diffusion/diffusion_random_1cluster_rho=p3_graph_visualization.png", dpi=300)
#plot_metrics_over_diffusion_two_axes(graphs)
#plt.savefig("figures/idealized_grids_diffusion/diffusion_random_1cluster_rho=p3_metrics_visualization.png", dpi=300)

#center 4
G = generate_center_grid(10, 10, node_pop)
graphs, rhos = diffuse(G, threshold=0.3)
visualize_diffusion(graphs, rhos)
plt.savefig("figures/idealized_grids_diffusion/diffusion_center_cluster_graph_visualization.png", dpi=300)
main_fig, legend_fig = plot_metrics_over_diffusion_two_axes(graphs)
main_fig.savefig("figures/idealized_grids_diffusion/diffusion_center_cluster_metrics_visualization_twoaxes.png", dpi=300, bbox_inches="tight")
legend_fig.savefig("figures/idealized_grids_diffusion/diffusion_center_cluster_metrics_visualization_twoaxes_legend.png", dpi=300, bbox_inches="tight")

#corner 4
#G = generate_2_corner_grid(10, 10, node_pop)
#graphs, rhos = diffuse(G, threshold=0.3)
#visualize_diffusion(graphs, rhos)
#plt.savefig("figures/idealized_grids_diffusion/diffusion_2_corner_cluster_graph_visualization.png", dpi=300)
#plot_metrics_over_diffusion_two_axes(graphs)
#plt.savefig("figures/idealized_grids_diffusion/diffusion_2_corner_cluster_metrics_visualization.png", dpi=300)

#center 4
#G = generate_outer_grid(10, 10, node_pop)
#graphs, rhos = diffuse(G, threshold=0.3)
#visualize_diffusion(graphs, rhos)
#plt.savefig("figures/idealized_grids_diffusion/diffusion_outer_cluster_graph_visualization.png", dpi=300)
#plot_metrics_over_diffusion_two_axes(graphs)
#plt.savefig("figures/idealized_grids_diffusion/diffusion_outer_cluster_metrics_visualization.png", dpi=300)