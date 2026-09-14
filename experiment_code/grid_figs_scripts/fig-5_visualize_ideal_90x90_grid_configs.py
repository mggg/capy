import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))          # for grid_figs_helpers
sys.path.insert(0, str(Path(__file__).parents[2]))      # for pipeline (2 levels up = capy-bara/)
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
from grid_figs_helpers import generate_ch_grid, generate_const_grid, generate_clust_grid, generate_isol_grid, generate_kclust_grid, draw_grid_as_checkerboard

"""
This script visualizes isolated, clustered, kclustered, and checkerboard configurations on a 90x90 polygonal grid. 

Global Parameters:
    RHO: float
        the minority proportion of the graphs being visualized
    nod_pop: int
        the population at each node
"""

RHO = 0.3
node_pop = 1

draw_grid_as_checkerboard(generate_ch_grid(90, 90, RHO, node_pop), "checkerboard", RHO)
draw_grid_as_checkerboard(generate_clust_grid(90, 90, RHO, node_pop, method = "random"), "clustered", RHO)
draw_grid_as_checkerboard(generate_isol_grid(90, 90, RHO, node_pop), "isolated", RHO)
draw_grid_as_checkerboard(generate_kclust_grid(90, 90, RHO, node_pop, 6, method = "random")[0], "kclustered", RHO)