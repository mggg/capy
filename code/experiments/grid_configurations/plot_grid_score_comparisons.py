"""Render binary and share-grid scores over their saved lattice reference arrangements."""

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.lines import Line2D
from plotting.figure_style import create_plot, create_score_scatter_plot, save_legend, save_plot
from plotting.grid_references import plot_grid_references
from plotting.grids import GRID_POP_SHARE_CMAP, plot_grid

from experiments.grid_configurations.grid_pop_share_arrangements import Arrangement

BINARY_COLORS = {
    "few_unlike": "#5B8C00",
    "intermediate": "#8A6500",
    "many_unlike": "#6F2365",
}
BINARY_MARKERS = {
    "few_unlike": "o",
    "intermediate": "^",
    "many_unlike": "s",
}
PROFILE_COLORS = {"moderate": "#3366CC", "many_mixed": "#BD33A4", "mostly_mixed": "#6F9500"}
ARRANGEMENT_MARKERS = {
    Arrangement.CLUSTERED: "o",
    Arrangement.RANDOM: "^",
    Arrangement.ALTERNATING: "s",
}
CELL_EDGE_COLOR = "#222222"
POINT_EDGE_COLOR = "white"


def plot_grid_score_comparisons(data_directory: Path, output_directory: Path) -> None:
    """Save grid snapshots and score comparisons with their separate legends.

    Args:
        data_directory (Path): Saved grid arrays, scores, and reference_scores.parquet.
        output_directory (Path): Figure root containing grids/ and scores/. Legends are saved
            beside the score plots.

    Raises:
        OSError: Saved inputs cannot be read or an image cannot be written.
    """
    grid_directory = output_directory / "grids"
    score_directory = output_directory / "scores"

    scores_df = pd.read_parquet(data_directory / "grid_scores.parquet")
    references_df = pd.read_parquet(data_directory / "reference_scores.parquet")

    with np.load(data_directory / "grid_arrays.npz") as grids:
        for _, example in scores_df.loc[scores_df.family.eq("binary")].iterrows():
            figure, axes = create_plot()
            plot_grid(
                axes,
                grids[example.example],
                cmap=GRID_POP_SHARE_CMAP,
                cell_edge_color=CELL_EDGE_COLOR,
            )
            save_plot(
                figure,
                grid_directory / f"grid_binary_{example.category}_sample_{example['sample']:02d}",
            )

    for family, selected_df in scores_df.groupby("family"):
        category_handles: dict[str, PathCollection] = {}
        arrangement_handles: dict[str, PathCollection] = {}
        reference_handles: list[Line2D] = []

        for metric in references_df.metric.unique():
            figure, axes = create_score_scatter_plot()
            reference_handles, category_handles, arrangement_handles = plot_grid_scores(
                axes, selected_df, references_df, metric
            )
            score_column = "capy_exact" if family == "binary" and metric == "capy" else metric
            save_plot(figure, score_directory / f"{family}_{score_column}_by_population_share")

        for category, handle in category_handles.items():
            handle.set_label(category.replace("_", " "))

        save_legend(
            list(category_handles.values()), score_directory / f"{family}_example_classes_legend"
        )
        save_legend(reference_handles, score_directory / f"{family}_reference_arrangements_legend")

        if family == "shares":
            for arrangement, handle in arrangement_handles.items():
                handle.set_label(arrangement)

            save_legend(
                list(arrangement_handles.values()), score_directory / "shares_arrangements_legend"
            )


def plot_grid_scores(
    axes: Axes, scores_df: pd.DataFrame, references_df: pd.DataFrame, metric: str
) -> tuple[list[Line2D], dict[str, PathCollection], dict[str, PathCollection]]:
    """Draw one grid family's score points and lattice references on supplied axes.

    All examples are balanced, so points lie at share 0.5 without jitter. References use quadratic
    Capy; binary points use distinct-person Capy. The shaded region is not a bound on binary scores.

    Args:
        axes (Axes): Caller-owned drawing destination, left open.
        scores_df (pd.DataFrame): One family's scores with explicit category and arrangement columns.
        references_df (pd.DataFrame): Saved analytic reference rows.
        metric (str): Reference score name; capy selects capy_exact for binary examples.

    Returns:
        tuple: Reference lines and category/arrangement scatter handles for separate legends.
    """
    reference_handles = plot_grid_references(axes, references_df, metric)
    family = scores_df.family.iloc[0]
    score_column = "capy_exact" if family == "binary" and metric == "capy" else metric
    category_handles = {}
    arrangement_handles = {}
    colors = BINARY_COLORS if family == "binary" else PROFILE_COLORS

    plotting_df = scores_df.copy()

    plotting_df = plotting_df.sample(frac=1, random_state=42)
    category_handles = {}
    arrangement_handles = {}

    for _, row in plotting_df.iterrows():
        category = str(row["category"])
        arrangement = row["arrangement"]

        if family == "binary":
            arrangement = None
            marker = BINARY_MARKERS[category]

        else:
            arrangement = Arrangement(row["arrangement"])
            marker = ARRANGEMENT_MARKERS[arrangement]

        points = axes.scatter(
            row["group_share"],
            row[score_column],
            s=24,
            alpha=1.0,
            color=colors[category],
            marker=marker,
            edgecolors=POINT_EDGE_COLOR,
            linewidths=0.3,
            clip_on=False,
            zorder=5,
        )
        category_handles.setdefault(category, points)

        if family != "binary" and arrangement not in arrangement_handles:
            arrangement_handles[arrangement] = axes.scatter(
                [],
                [],
                s=24,
                color="black",
                marker=marker,
                edgecolors=POINT_EDGE_COLOR,
                linewidths=0.3,
            )

    return reference_handles, category_handles, arrangement_handles
