"""Independent count/share snapshots and early stochastic score trajectories."""

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
from plotting.grids import COUNT_CMAP, SHARE_CMAP, plot_grid

from experiments.synthetic_diffusion.stochastic_diffusion import DEMOGRAPHIES


def plot_stochastic_diffusion(data_directory: Path, output_directory: Path) -> None:
    """Render saved snapshots and prepared medians with pointwise 10th–90th percentile bands.

    The snapshot trajectories are independent examples, not medians or members of the cached
    replicate sample. Count colors saturate at 1,000 people, matching the fixed initial-cell scale.

    Args:
        data_directory (Path): Result root containing one_sided and two_sided subfolders.
        output_directory (Path): Figure root, using the same movement subfolder names.

    Raises:
        FileNotFoundError: No movement trace summaries are present.
        OSError: Results cannot be read or a PNG cannot be written.
    """
    summary_paths = sorted(data_directory.glob("*/stochastic_trace_summary.parquet"))

    if not summary_paths:
        raise FileNotFoundError(f"No stochastic movement results in {data_directory}")

    for summary_path in summary_paths:
        movement_directory = summary_path.parent
        plot_stochastic_movement(movement_directory, output_directory / movement_directory.name)


def plot_stochastic_movement(data_directory: Path, output_directory: Path) -> None:
    """Draw one movement rule's snapshots, score traces, legends, and colorbars.

    Args:
        data_directory (Path): One movement rule's saved trace quantiles and snapshots.
        output_directory (Path): Destination for its PNGs, with legends beside the plots.

    Raises:
        OSError: A saved result cannot be read or a figure cannot be written.
        ValueError: The trace summary does not identify exactly one movement rule.
    """
    trace_summary_df = pd.read_parquet(data_directory / "stochastic_trace_summary.parquet")
    (movement_rule,) = trace_summary_df["movement"].unique()

    with np.load(data_directory / "stochastic_states.npz") as snapshot_archive:
        snapshot_steps = snapshot_archive["snapshot_steps"]

        for demography in DEMOGRAPHIES:
            trajectory_name = f"{movement_rule}_{demography}"
            demography_abbreviation = {"constant": "const", "growth": "inc", "decline": "dec"}[
                demography
            ]

            for step, (first_group_population, second_group_population) in zip(
                snapshot_steps, snapshot_archive[trajectory_name], strict=True
            ):
                snapshot_stem = f"{demography_abbreviation}_{movement_rule}_stoc"
                figure, axes = create_plot()
                plot_grid(
                    axes,
                    first_group_population / (first_group_population + second_group_population),
                )
                save_plot(figure, output_directory / f"{step:03d}_share_diff_{snapshot_stem}")

                figure, axes = create_plot()
                plot_grid(axes, first_group_population, cmap=COUNT_CMAP, maximum=1000)
                save_plot(figure, output_directory / f"{step:03d}_pop_diff_{snapshot_stem}")

    for metric_name in ("capy", "dissimilarity", "entropy_index", "moran_comparison"):
        figure, axes = create_trace_plot()
        legend_handles = plot_stochastic_trace(axes, trace_summary_df, metric_name)
        save_plot(
            figure,
            output_directory / f"{movement_rule}_stochastic_diffusion_{metric_name}_by_step",
        )

        if metric_name == "capy":
            save_legend(legend_handles, output_directory / "demography_legend")
        elif metric_name == "moran_comparison":
            save_legend(legend_handles, output_directory / "moran_conventions_legend")

    save_colorbar(output_directory / "share_colorbar", SHARE_CMAP, 0, 1)
    save_colorbar(output_directory / "population_colorbar", COUNT_CMAP, 0, 1000)


def plot_stochastic_trace(
    axes: Axes, trace_summary_df: pd.DataFrame, metric_name: str
) -> list[Line2D]:
    """Draw one movement's prepared medians and percentile bands on caller-owned axes.

    Args:
        axes (Axes): Drawing destination, left open for adjustments.
        trace_summary_df (pd.DataFrame): One movement's step/demography/quantile rows
            with score columns.
        metric_name (str): Score column, or moran_comparison for both Moran conventions.

    Returns:
        list[Line2D]: Plotted lines for a separate legend.
    """
    legend_handles = []

    for demography, demographic_color in DIFFUSION_DEMOGRAPHIC_COLORS.items():
        demographic_summary_df = trace_summary_df.loc[trace_summary_df.demography.eq(demography)]
        metric_colors = (
            MORAN_COLORS if metric_name == "moran_comparison" else {metric_name: demographic_color}
        )

        for metric_column, color in metric_colors.items():
            score_quantiles_df = demographic_summary_df.pivot(
                index="step", columns="quantile", values=metric_column
            )
            legend_label = demography

            if metric_name == "moran_comparison":
                legend_label = (
                    "Moran (I + A)"
                    if metric_column == "moran_with_self"
                    else "Moran (row-standardized)"
                )

            median_line = axes.plot(
                score_quantiles_df.index,
                score_quantiles_df[0.5],
                color=color,
                lw=2.2,
                alpha=0.55 if metric_name == "moran_comparison" else 1,
                label=legend_label,
            )[0]
            axes.fill_between(
                score_quantiles_df.index,
                score_quantiles_df[0.1],
                score_quantiles_df[0.9],
                color=color,
                alpha=0.045 if metric_name == "moran_comparison" else 0.12,
            )

            if metric_name != "moran_comparison" or demography == "constant":
                legend_handles.append(median_line)

    axes.set_ylim(-0.08 if metric_name == "moran_comparison" else -0.02, 1.02)
    return legend_handles
