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
from grid_figs_helpers import generate_ch_grid, generate_const_grid, generate_clust_grid, generate_isol_grid, generate_kclust_grid, draw_grid_as_checkerboard

RHO = 0.3

draw_grid_as_checkerboard(generate_ch_grid(90, 90, RHO, 1000), "checkerboard", RHO)
draw_grid_as_checkerboard(generate_clust_grid(90, 90, RHO, 1000, method = "random"), "clustered", RHO)
draw_grid_as_checkerboard(generate_isol_grid(90, 90, RHO, 1000), "isolated", RHO)
draw_grid_as_checkerboard(generate_kclust_grid(90, 90, RHO, 1000, 6, method = "random")[0], "kclustered", RHO)
