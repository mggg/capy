"""Individual grid snapshots with explicit population scales."""

import numpy as np
from matplotlib.axes import Axes
from matplotlib.colors import Colormap, LinearSegmentedColormap

SHARE_CMAP = LinearSegmentedColormap.from_list("group_share", ["#f5f2e9", "#008080"])
GRID_POP_SHARE_CMAP = LinearSegmentedColormap.from_list(
    "grid_population_share", ["#0878C1", "#8B4AA5", "#ED1C24"]
)


CELL_EDGE_COLOR = "white"


def plot_grid(
    axes: Axes,
    grid: np.ndarray,
    *,
    cmap: Colormap = SHARE_CMAP,
    maximum: float = 1,
    cell_edge_color: str = CELL_EDGE_COLOR,
) -> None:
    """Draw one grid with a fixed color scale and visible cell boundaries.

    Args:
        axes (Axes): Caller-owned axes to draw on; left open for further adjustments.
        grid (np.ndarray): Two-dimensional shares or population counts.
        cmap (Colormap): Color scale; defaults to cream–teal for diffusion shares.
        maximum (float): Upper color limit, default 1. Values above it saturate the scale.
        cell_edge_color (str): Cell boundary color, default white.
    """
    axes.imshow(grid, vmin=0, vmax=maximum, cmap=cmap, interpolation="nearest")
    axes.grid(False)
    axes.set_xticks(np.arange(-0.5, grid.shape[1], 1), minor=True)
    axes.set_yticks(np.arange(-0.5, grid.shape[0], 1), minor=True)
    axes.grid(which="minor", color=cell_edge_color, linewidth=0.3, alpha=0.5)
    axes.tick_params(which="both", bottom=False, left=False, labelbottom=False, labelleft=False)
