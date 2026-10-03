"""Render the nine saved grid configurations as independent panels."""

from pathlib import Path

import numpy as np
from plotting.figure_style import create_plot, save_colorbar, save_plot
from plotting.grids import GRID_POP_SHARE_CMAP, plot_grid

CELL_EDGE_COLOR = "#222222"


def plot_grid_pop_share_arrangements(data_directory: Path, output_directory: Path) -> None:
    """Render saved share grids and a separate color scale.

    Args:
        data_directory (Path): Folder containing share_grids.npz.
        output_directory (Path): Destination for individual grids and the color scale.

    Raises:
        OSError: An array archive cannot be read or a component cannot be written.
    """
    with np.load(data_directory / "share_grids.npz") as grids:
        for name in grids.files:
            figure, axes = create_plot()
            plot_grid(
                axes,
                grids[name],
                cmap=GRID_POP_SHARE_CMAP,
                cell_edge_color=CELL_EDGE_COLOR,
            )

            save_plot(figure, output_directory / f"grid_{name}")

    save_colorbar(output_directory / "share_colorbar", GRID_POP_SHARE_CMAP, 0, 1)
