"""Render saved analytic arrangement curves as individual score panels."""

from pathlib import Path

import pandas as pd
from plotting.figure_style import create_score_scatter_plot, save_legend, save_plot
from plotting.grid_references import plot_grid_references


def plot_grid_reference_scores(data_directory: Path, output_directory: Path) -> None:
    """Read analytic scores and export ten framed panels plus a separate reference legend.

    Args:
        data_directory (Path): Folder containing theoretical_scores.parquet.
        output_directory (Path): Destination for independent 300 dpi PNG components.

    Raises:
        OSError: A score table cannot be read or an output cannot be written.
    """
    scores_df = pd.read_parquet(data_directory / "theoretical_scores.parquet")

    handles = []

    for metric in scores_df.metric.unique():
        figure, axes = create_score_scatter_plot()
        handles = plot_grid_references(axes, scores_df, metric)
        save_plot(figure, output_directory / f"{metric}_by_population_share")

    save_legend(handles, output_directory / "reference_arrangements_legend")
