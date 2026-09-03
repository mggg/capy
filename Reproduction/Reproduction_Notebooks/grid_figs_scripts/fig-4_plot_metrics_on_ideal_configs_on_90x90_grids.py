import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))          # for grid_figs_helpers
sys.path.insert(0, str(Path(__file__).parents[3]))      # for pipeline (3 levels up = capy-bara/)     # for pipeline (3 levels up = capy-bara/)
import pipeline.metrics as metrics
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import gerrychain.grid
import random
from collections import deque
import warnings
random.seed(42)
import seaborn as sns
from grid_figs_helpers import generate_ch_grid, generate_const_grid, generate_clust_grid, generate_isol_grid, generate_kclust_grid

METHOD = "random" # "bfs" or "random"

graphs_ch = []
graphs_const = []
graphs_clust = [] 
graphs_isol = []


rhos = np.linspace(.1, .5, 5)

for rho in rhos: 
    graphs_ch.append(generate_ch_grid(90, 90, rho, 1000))
    graphs_const.append(generate_const_grid(90, 90, rho, 1000))
    graphs_clust.append(generate_clust_grid(90, 90, rho, 1000, method = METHOD))
    graphs_isol.append(generate_isol_grid(90, 90, rho, 1000))

half_edge_ch = [metrics.half_edge(G.graph, "x_pop", "y_pop") for G in graphs_ch]
half_edge_const = [metrics.half_edge(G.graph, "x_pop", "y_pop") for G in graphs_const]
half_edge_clust = [metrics.half_edge(G.graph, "x_pop", "y_pop") for G in graphs_clust]
half_edge_isol = [metrics.half_edge(G.graph, "x_pop", "y_pop") for G in graphs_isol]

half_edge_kclust = []
kclust_labels = []

# accumulate as list of tuples
graphs_kclust = []
for rho in rhos:
    G, real_rho, num_components = generate_kclust_grid(90, 90, rho, 1000, k=8, method=METHOD)
    graphs_kclust.append((G, real_rho, num_components))

half_edge_kclust = [metrics.half_edge(G.graph, "x_pop", "y_pop") for G, _, _ in graphs_kclust]
x_vals_kclust = [real_rho for _, real_rho, _ in graphs_kclust]

# line goes in legend normally

# annotate each point — not in legend
for (_, real_rho, num_components), y in zip(graphs_kclust, half_edge_kclust):
    plt.annotate(
        f"{num_components}\nclusters",
        xy=(real_rho, y),
        xytext=(0, -20),
        textcoords="offset points",
        ha="center",
        fontsize=6,
    )


plt.plot(rhos, half_edge_ch,    label="Checkerboard", marker="o")
plt.plot(rhos, half_edge_const, label="Constant",     marker="o")
plt.plot(rhos, half_edge_clust, label="One Cluster",    marker="o")
plt.plot(x_vals_kclust, half_edge_kclust, label="Multiple Clusters", marker="o")
plt.plot(rhos, half_edge_isol,  label="Isolated",     marker="o")


plt.legend(fontsize=8, handlelength=1.5, handleheight=.75, handletextpad=0.4, borderpad=0.4)
plt.xlabel("Minority Proportion")
plt.ylabel("Capy")
plt.savefig(f"Reproduction/Reproduction_Figures/Idealized_Grids/fig-4_capy_on_idealized_grids_{METHOD}_clusters.png", dpi=150, bbox_inches="tight")

