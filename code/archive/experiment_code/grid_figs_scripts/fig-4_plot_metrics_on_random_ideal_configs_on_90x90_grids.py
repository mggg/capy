"""Plot Capy against achieved minority share for sampled 90 by 90 grid configurations.

The configurations are isolated, single-cluster, and multiple-cluster arrangements. Assigning whole
nodes can make the achieved share differ from its target.

Global Parameters:
    METHOD (str): "random" for randomized cluster growth or "bfs" for breadth-first growth.
    num_rhos (int): Number of evenly spaced target shares between 0.1 and 0.5.
    num_samples (int): Number of sampling rounds over the target shares.
    node_pop (int): Population per node.
    num_seeds (int): Number of starting nodes for multiple-cluster configurations.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # for grid_figs_helpers
sys.path.insert(
    0, str(Path(__file__).parents[2])
)  # Repository root for capy_core imports.
import capy_core.metrics as metrics
import matplotlib.pyplot as plt
import numpy as np
import random

random.seed(42)
from grid_figs_helpers import (
    generate_clust_grid,
    generate_isol_grid,
    generate_kclust_grid,
)


plt.rcParams.update(
    {
        "font.family": "serif",
        "mathtext.fontset": "cm",
        "font.size": 11,
        "savefig.dpi": 300,
    }
)

METHOD = "random"  # "bfs" or "random"
num_rhos = 20
num_samples = 20
node_pop = 1
num_seeds = 4

graphs_clust = []
graphs_isol = []
graphs_kclust = []

for _ in range(num_samples):
    rhos = np.linspace(0.1, 0.5, num_rhos)

    for rho in rhos:
        graphs_clust.append(generate_clust_grid(90, 90, rho, node_pop, method=METHOD))
        graphs_isol.append(generate_isol_grid(90, 90, rho, node_pop))
        result = generate_kclust_grid(90, 90, rho, node_pop, num_seeds, method=METHOD)
        if result is not None:
            G, real_rho, num_components = generate_kclust_grid(
                90, 90, rho, node_pop, num_seeds, method=METHOD
            )
            graphs_kclust.append(result)
        graphs_kclust.append((G, real_rho, num_components))

half_edge_clust = [
    metrics.half_edge(G.graph, "x_pop", "y_pop") for G, _ in graphs_clust
]
half_edge_isol = [metrics.half_edge(G.graph, "x_pop", "y_pop") for G, _ in graphs_isol]
half_edge_kclust = [
    metrics.half_edge(G.graph, "x_pop", "y_pop") for G, _, _ in graphs_kclust
]
x_vals_clust = [real_rho for _, real_rho in graphs_clust]
x_vals_isol = [real_rho for _, real_rho in graphs_isol]
x_vals_kclust = [real_rho for _, real_rho, _ in graphs_kclust]


plt.scatter(
    x_vals_clust,
    half_edge_clust,
    label="One Cluster",
    s=10,
    color="#006B3C",
    edgecolors="black",
    linewidths=0.5,
)
plt.scatter(
    x_vals_kclust,
    half_edge_kclust,
    label="Multiple Clusters",
    s=10,
    color="#8db600",
    edgecolors="black",
    linewidths=0.5,
)
plt.scatter(
    x_vals_isol,
    half_edge_isol,
    label="Isolated",
    s=10,
    color="#69359c",
    edgecolors="black",
    linewidths=0.5,
)

plt.legend(
    fontsize=8, handlelength=1.5, handleheight=0.75, handletextpad=0.4, borderpad=0.4
)
handles, labels = plt.gca().get_legend_handles_labels()
plt.legend().remove()
plt.savefig(
    f"figures/idealized_grids/fig-4_capyx_v_rhoy_scatterplots_90x90_random_configs_{num_samples}samples_{num_rhos}rhos_{num_seeds}seeds_mainplot.png",
    dpi=300,
    bbox_inches="tight",
)

legend_fig, legend_ax = plt.subplots()
legend_ax.axis("off")
legend_ax.legend(
    handles,
    labels,
    loc="center",
    fontsize=8,
    handlelength=1.5,
    handleheight=0.75,
    handletextpad=0.4,
    borderpad=0.4,
)
legend_fig.set_size_inches(1, 0.25)
plt.savefig(
    f"figures/idealized_grids/fig-4_capyx_v_rhoy_scatterplots_90x90_random_configs_{num_samples}samples_{num_rhos}rhos_{num_seeds}seed_legend.png",
    dpi=300,
    bbox_inches="tight",
)
