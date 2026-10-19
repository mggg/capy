"""Separate configuration snapshots and score traces for expanding-support experiments."""

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from plotting.figure_style import (
    DIFFUSION_DEMOGRAPHIC_COLORS,
    MORAN_COLORS,
    create_plot,
    create_trace_plot,
    save_colorbar,
    save_legend,
    save_plot,
)
from plotting.grids import SHARE_CMAP, plot_grid

from experiments.synthetic_diffusion.expanding_support import Demography, SupportShape


def plot_expanding_support(data_directory: Path, output_directory: Path) -> None:
    """Render each saved shape into its own folder, including its legends and colorbar.

    Args:
        data_directory (Path): Root containing one result subfolder per shape.
        output_directory (Path): Figure root, using the same shape subfolder names.

    Raises:
        FileNotFoundError: No shape score tables are present.
        OSError: A result cannot be read or a figure cannot be written.
    """
    score_paths = sorted(data_directory.glob("*/expanding_support_scores.parquet"))

    if not score_paths:
        raise FileNotFoundError(f"No expanding-support shape results in {data_directory}")

    for score_path in score_paths:
        shape_directory = score_path.parent
        plot_expanding_support_shape(shape_directory, output_directory / shape_directory.name)


def plot_expanding_support_shape(data_directory: Path, output_directory: Path) -> None:
    """Render six snapshots per trajectory, four score plots per shape, and separate legends.

    Args:
        data_directory (Path): One shape's saved expanding-support arrays and scores.
        output_directory (Path): Destination for named snapshots, traces, and legends.

    Raises:
        OSError: An input cannot be read or a PNG cannot be written.
        ValueError: The score table does not identify exactly one supported shape.
    """
    scores_df = pd.read_parquet(data_directory / "expanding_support_scores.parquet")
    (shape_value,) = scores_df["shape"].unique()
    shape = SupportShape(shape_value)
    shape_name = {
        SupportShape.CENTERED_RECTANGLE: "cen_rect",
        SupportShape.ROOK_EXPANDING_CORE: "rook_core",
        SupportShape.THICK_CROSS: "thick_cross",
    }[shape]
    coordinate = (
        "expansion_progress" if shape == SupportShape.ROOK_EXPANDING_CORE else "support_fraction"
    )

    with np.load(data_directory / "states.npz") as states:
        for demography, abbreviation in (
            (Demography.CONSTANT, "const"),
            (Demography.GROWTH, "inc"),
            (Demography.DECLINE, "dec"),
        ):
            grids = states[f"{shape}_{demography}"]
            snapshot_name = f"{abbreviation}_{shape_name}"

            for step in np.rint(np.linspace(0, len(grids) - 1, 6)).astype(int):
                figure, axes = create_plot()
                plot_grid(axes, grids[step])
                save_plot(figure, output_directory / f"{step:02d}_{snapshot_name}_diffusion")

    demographic_handles = []

    for metric in ("dissimilarity", "entropy_index", "capy"):
        figure, axes = create_trace_plot()
        demographic_handles = plot_expanding_support_trace(axes, scores_df, metric, coordinate)
        axes.set_ylim(-0.02, 1.02)
        save_plot(figure, output_directory / f"{shape_name}_diffusion_{metric}_by_{coordinate}")

    save_legend(demographic_handles, output_directory / "demography_legend")

    figure, axes = create_trace_plot()
    moran_handles = plot_expanding_support_moran_comparison(axes, scores_df, coordinate)
    axes.set_ylim(-0.08, 1.02)
    save_plot(figure, output_directory / f"{shape_name}_diffusion_moran_comparison_by_{coordinate}")
    save_legend(moran_handles, output_directory / "moran_conventions_legend")
    save_colorbar(output_directory / "share_colorbar", SHARE_CMAP, 0, 1)


def plot_expanding_support_trace(
    axes: Axes, scores_df: pd.DataFrame, metric: str, coordinate: str
) -> list[Line2D]:
    """Draw one score for the constant, growing, and declining populations of a shape.

    Args:
        axes (Axes): Caller-owned drawing destination, left open for adjustments.
        scores_df (pd.DataFrame): One shape's saved scores.
        metric (str): Score column to draw for each demography.
        coordinate (str): Saved support_fraction or expansion_progress column for the x axis.

    Returns:
        list[Line2D]: Actual plotted lines for a separate demographic legend.
    """
    handles = []

    for demography in Demography:
        selected_df = scores_df.loc[scores_df.demography.eq(demography)].sort_values(coordinate)
        (line,) = axes.plot(
            selected_df[coordinate],
            selected_df[metric],
            color=DIFFUSION_DEMOGRAPHIC_COLORS[demography],
            lw=2.2,
            label=demography,
        )
        handles.append(line)

    return handles


def plot_expanding_support_moran_comparison(
    axes: Axes, scores_df: pd.DataFrame, coordinate: str
) -> list[Line2D]:
    """Compare closed-neighborhood and row-standardized Moran on the constant trajectory.

    Multiplying all cell shares by a common scalar leaves Moran unchanged, so one demographic
    trajectory suffices. Its uniform final state is undefined and remains a gap.

    Args:
        axes (Axes): Caller-owned drawing destination, left open for adjustments.
        scores_df (pd.DataFrame): One shape's saved scores, including the constant trajectory.
        coordinate (str): Saved support_fraction or expansion_progress column for the x axis.

    Returns:
        list[Line2D]: Actual plotted lines for a separate Moran-convention legend.
    """
    constant_df = scores_df.loc[scores_df.demography.eq(Demography.CONSTANT)].sort_values(
        coordinate
    )
    handles = []

    for convention, label in (
        ("moran_with_self", "Moran (I + A)"),
        ("moran_row_standardized", "Moran (row-standardized)"),
    ):
        (line,) = axes.plot(
            constant_df[coordinate],
            constant_df[convention],
            color=MORAN_COLORS[convention],
            lw=2.2,
            label=label,
        )
        handles.append(line)

    return handles
