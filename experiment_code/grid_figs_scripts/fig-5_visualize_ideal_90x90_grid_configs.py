"""Visualize isolated, clustered, multiple-cluster, and checkerboard grids.

Each configuration uses a 90 by 90 polygonal grid.

Global Parameters:
    RHO (float): Target minority population share.
    node_pop (int): Population per node.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # for grid_figs_helpers
sys.path.insert(
    0, str(Path(__file__).parents[2])
)  # Repository root for capy_core imports.
import random

random.seed(42)
from grid_figs_helpers import (
    generate_ch_grid,
    generate_clust_grid,
    generate_isol_grid,
    generate_kclust_grid,
    draw_grid_as_checkerboard,
)


RHO = 0.3
node_pop = 1

draw_grid_as_checkerboard(generate_ch_grid(90, 90, RHO, node_pop), "checkerboard", RHO)
draw_grid_as_checkerboard(
    generate_clust_grid(90, 90, RHO, node_pop, method="random")[0], "clustered", RHO
)
draw_grid_as_checkerboard(generate_isol_grid(90, 90, RHO, node_pop)[0], "isolated", RHO)
result = generate_kclust_grid(
    90, 90, RHO, node_pop, 4, method="random", max_retries=10000
)
if result is not None:
    draw_grid_as_checkerboard(result[0], "4clustered", RHO)
