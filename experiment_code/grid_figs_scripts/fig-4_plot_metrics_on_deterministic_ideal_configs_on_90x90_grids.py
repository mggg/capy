import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))          # for grid_figs_helpers
sys.path.insert(0, str(Path(__file__).parents[2]))      # for pipeline (2 levels up = capy-bara/)     # for pipeline (3 levels up = capy-bara/)
import capy_core.metrics as metrics
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

"""
This script generates lineplots of capy versus rho for constant and checkerboard configurations for a set number of global values of rho.
Global Parameters:
    num_rhos: int
        Set a number of evenly spaced rhos between .1 and .5. The script plots values of capy for checkerboard and constant configurations of those rhos
    node_pop: int
        How many people live in each node
"""

plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm", #setting to latex font
                    "font.size": 11, "savefig.dpi": 300})

node_pop = 1
num_rhos = 5

graphs_ch = []
graphs_const = []

rhos = np.linspace(.1, .5, num_rhos)

for rho in rhos: 
    graphs_ch.append(generate_ch_grid(90, 90, rho, node_pop))
    graphs_const.append(generate_const_grid(90, 90, rho, node_pop))

half_edge_ch = [metrics.half_edge(G.graph, "x_pop", "y_pop") for G in graphs_ch]
half_edge_const = [metrics.half_edge(G.graph, "x_pop", "y_pop") for G in graphs_const]

plt.plot(rhos, half_edge_ch,    label="Checkerboard", marker="o", color = "#1560bd")
plt.plot(rhos, half_edge_const, label="Constant",     marker="o", color = "#ffa812")

plt.legend(fontsize=8, handlelength=1.5, handleheight=.75, handletextpad=0.4, borderpad=0.4)
handles, labels = plt.gca().get_legend_handles_labels()
plt.legend().remove()

plt.savefig(f"figures/idealized_grids/fig-4_capyx_v_rhoy_lineplot_90x90_deterministic_configs_nodepop={node_pop}_{num_rhos}rhos_mainplot.png", dpi=300, bbox_inches="tight")

legend_fig, legend_ax = plt.subplots()
legend_ax.axis("off")
legend_ax.legend(handles, labels, loc="center",
                 fontsize=8, handlelength=1.5, handleheight=.75,
                 handletextpad=0.4, borderpad=0.4)
legend_fig.set_size_inches(1.5, .5)
plt.savefig(f"figures/idealized_grids/fig-4_capyx_v_rhoy_lineplot_90x90_deterministic_configs_nodepop={node_pop}_{num_rhos}rhos_legend.png", dpi=300, bbox_inches="tight")

