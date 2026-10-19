"""Render four binary group arrangements on triangular lattices."""

from pathlib import Path

import numpy as np
from plotting.figure_style import create_plot, save_plot

PATTERN_NAMES = {
    "printed_upper_left": "dispersed_sparse_population",
    "printed_upper_right": "dispersed_denser_population",
    "printed_lower_left": "large_population_clusters",
    "printed_lower_right": "small_population_clusters",
}

FIRST_GROUP_COLOR = "black"
SECOND_GROUP_COLOR = "white"
NODE_EDGE_COLOR = "black"


def plot_triangular_lattices(data_directory: Path, output_directory: Path) -> None:
    """Export the four printed arrangements without adding periodic dots or score annotations.

    Args:
        data_directory (Path): Folder containing triangular_windows.npz from the experiment.
        output_directory (Path): Destination for four independent lattice PNG components.

    Raises:
        OSError: Saved windows cannot be read or a component cannot be written.
        ValueError: Saved windows are not readable NumPy arrays with two dimensions.
    """
    with np.load(data_directory / "triangular_windows.npz") as windows:
        for name in windows.files:
            if not name.startswith("printed_"):
                continue

            figure, axes = create_plot()
            window = windows[name]

            row_indices, column_indices = np.indices(window.shape)
            axes.scatter(
                column_indices.ravel() - 0.5 * (row_indices.ravel() % 2),
                -np.sqrt(3) / 2 * row_indices.ravel(),
                facecolors=np.where(window.ravel(), FIRST_GROUP_COLOR, SECOND_GROUP_COLOR),
                edgecolors=NODE_EDGE_COLOR,
                linewidths=1,
                s=100,
            )
            axes.set_aspect("equal")
            axes.set_axis_off()
            save_plot(figure, output_directory / PATTERN_NAMES[name])
