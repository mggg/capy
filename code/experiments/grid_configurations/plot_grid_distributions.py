"""Draw binary grid examples and histograms of their saved scores."""

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.colors import ListedColormap
from plotting.figure_style import DARK_TANGERINE, DENIM, create_plot, save_plot

AXIS_COLOR = "#dddddd"
CELL_EDGE_COLOR = "white"
SAMPLE_MEAN_COLOR = "#777777"


def plot_grid_distributions(data_directory: Path, output_directory: Path) -> None:
    """Export three binary examples and six histograms with a dashed sample-mean line.

    Each histogram uses twenty bins over its observed range, while the displayed metric range
    stays fixed across clustering classes. Classes share a vertical scale within each metric,
    enlarged when necessary so that no histogram bar is clipped.

    Args:
        data_directory (Path): Folder containing the saved score table and example grids.
        output_directory (Path): Destination for individual grid and histogram PNGs.

    Raises:
        OSError: Saved inputs cannot be read or an image cannot be written.
    """
    scores_df = pd.read_parquet(data_directory / "distribution_scores.parquet")

    with np.load(data_directory / "distribution_examples.npz") as grids:
        for clustering in grids.files:
            figure, axes = create_plot()
            plot_binary_grid(axes, grids[clustering])
            save_plot(figure, output_directory / f"grid_{clustering}_clustering")

    for metric in ("capy", "moran_row_standardized"):
        maximum_count = max(
            np.histogram(class_scores_df[metric], bins=20)[0].max()
            for _, class_scores_df in scores_df.groupby("kind")
        )

        count_limit = max(1800, maximum_count * 1.05)

        for clustering, class_scores_df in scores_df.groupby("kind"):
            figure, axes = create_plot()
            figure.set_size_inches(3.4, 2.04)
            plot_grid_score_distribution(axes, class_scores_df, metric, count_limit)
            save_plot(figure, output_directory / f"{clustering}_clustering_{metric}_histogram")


def plot_binary_grid(axes: Axes, grid: np.ndarray) -> None:
    """Draw one binary configuration on the supplied axes.

    Args:
        axes (Axes): Caller-owned destination for the grid.
        grid (np.ndarray): Two-dimensional binary population arrangement.
    """
    axes.pcolormesh(
        grid,
        cmap=ListedColormap([DARK_TANGERINE, DENIM]),
        vmin=0,
        vmax=1,
        edgecolors=CELL_EDGE_COLOR,
        linewidth=0.3,
    )
    axes.set_aspect("equal")
    axes.set_axis_off()


def plot_grid_score_distribution(
    axes: Axes, scores_df: pd.DataFrame, metric: str, maximum_count: float
) -> None:
    """Draw one clustering class's histogram and mean on caller-owned axes.

    Args:
        axes (Axes): Drawing destination, left open for adjustments.
        scores_df (pd.DataFrame): One clustering class's sample scores.
        metric (str): capy or moran_row_standardized score column.
        maximum_count (float): Shared upper count limit across clustering classes.
    """
    limits = (0, 1) if metric == "capy" else (-1, 1)
    color = DENIM if metric == "capy" else DARK_TANGERINE
    axes.hist(scores_df[metric], bins=20, color=color, alpha=0.6, edgecolor="none")

    axes.spines[["left", "bottom"]].set_visible(True)
    axes.spines[["left", "bottom"]].set_color(AXIS_COLOR)

    axes.axvline(
        float(np.mean(scores_df[metric].to_numpy(dtype=float))),
        color=SAMPLE_MEAN_COLOR,
        linestyle="--",
        lw=0.8,
    )

    axes.set(xlim=limits, ylim=(0, maximum_count), yticks=[])
    axes.grid(False)
