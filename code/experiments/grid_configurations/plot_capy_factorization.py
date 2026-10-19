"""Render saved Capy factorization experiments as separate publication panels."""

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize, PowerNorm, to_rgb
from matplotlib.figure import Figure
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import FuncFormatter
from plotting.figure_style import create_plot, save_legend, save_plot, write_figure_png
from skimage.color import lab2rgb, rgb2lab

from experiments.grid_configurations.capy_factorization import (
    EXAMPLE_SHARE_TARGETS,
    FactorQuadrant,
    SelectedExample,
)
from experiments.grid_configurations.factorization_layout import GRID_SIDE_LENGTH

QUADRANT_COLORS = {
    FactorQuadrant.WEAK_CLUSTERED: "#008080",
    FactorQuadrant.STRONG_CLUSTERED: "#E62020",
    FactorQuadrant.WEAK_DISPERSED: "#89CFF0",
    FactorQuadrant.STRONG_DISPERSED: "#FFBF00",
}
SCORE_COLUMNS = (
    "dissimilarity",
    "entropy_index",
    "relative_diversity",
    "spatial_dissimilarity",
    "spatial_entropy_index",
    "spatial_relative_diversity",
    "moran_with_self",
    "capy",
)


class FactorizationPanelStyle(Enum):
    """Panel appearances for all grids, selected targets, gradients, and exposure comparisons."""

    ALL_GRIDS = auto()
    SELECTED_TARGETS = auto()
    GRADIENT = auto()
    EXPOSURE_COMPARISON = auto()


@dataclass(frozen=True)
class FactorizationPlotData:
    """Matched score tables and example grids, loaded independently of open files.

    selected_scores_df repeats score rows when a seed serves multiple selection targets.
    example_grids contains only rank-one selections. Renderers treat all arrays and tables as
    read-only; table shuffling creates a separate table.
    """

    scores_df: pd.DataFrame
    selected_scores_df: pd.DataFrame
    example_grids: dict[SelectedExample, np.ndarray]


def plot_capy_factorization(data_directory: Path, output_directory: Path) -> None:
    """Draw factor/score comparisons, gradients, individual grids, and two-by-two grid groups.

    Reads factorization_scores.parquet, selected_examples.parquet, and grids.npz. Colors and
    numeric axes are included; titles and labels are left to document assembly except for the
    share targets on grouped grids. Every PNG is 300 dpi. exposure_comparison/ uses wider panels
    for Capy, spatial entropy, isolation, and exposure.

    Args:
        data_directory (Path): Saved result root from run_capy_factorization().
        output_directory (Path): Destination for panel sets and separate legends/colorbars.

    Raises:
        OSError: An input cannot be read or output written.
        ValueError: Saved seed identities are duplicated or inconsistent, grid shapes are
            incorrect, a quadrant is unsupported, or a grid group lacks its four share targets.
        KeyError: A required column or grid array is missing.
    """
    plot_data = read_factorization_plot_data(data_directory)
    scores_df = plot_data.scores_df
    selected_scores_df = plot_data.selected_scores_df

    scores_df = scores_df.iloc[np.random.default_rng(0).permutation(len(scores_df))]
    selected_scores_df = selected_scores_df.iloc[
        np.random.default_rng(0).permutation(len(selected_scores_df))
    ]
    colors = build_faded_quadrant_colors(
        scores_df["intensity"].to_numpy(), scores_df["layout"].to_numpy()
    )
    plot_factorization_panels(
        scores_df,
        colors,
        output_directory / "all_quadrants",
        panel_style=FactorizationPanelStyle.ALL_GRIDS,
    )

    plot_factorization_panels(
        scores_df,
        colors,
        output_directory / "exposure_comparison",
        panel_style=FactorizationPanelStyle.EXPOSURE_COMPARISON,
        metrics=("capy", "spatial_entropy_index", "x_isolation", "y_to_x_exposure"),
    )

    selected_colors = np.array(
        [to_rgb(QUADRANT_COLORS[name]) for name in selected_scores_df["quadrant"]]
    )
    plot_factorization_panels(
        selected_scores_df,
        selected_colors,
        output_directory / "selected_targets",
        panel_style=FactorizationPanelStyle.SELECTED_TARGETS,
    )

    plot_factorization_gradients(scores_df, output_directory)
    plot_factorization_examples(plot_data.example_grids, output_directory / "grids")
    plot_factorization_groups(plot_data.example_grids, output_directory / "grids_2x2")
    save_legend(
        [
            Patch(facecolor=color, label=name.replace("_", " "))
            for name, color in QUADRANT_COLORS.items()
        ],
        output_directory / "quadrants_legend",
    )
    _save_factorization_colorbar(
        output_directory / "grid_share_colorbar", "Greys", Normalize(0, 1), (0, 0.5, 1), 3.696
    )


def read_factorization_plot_data(data_directory: Path) -> FactorizationPlotData:
    """Load scores and selections, matching example arrays by seed before any figure is drawn.

    Args:
        data_directory (Path): Folder containing factorization_scores.parquet,
            selected_examples.parquet, and grids.npz.

    Returns:
        FactorizationPlotData: Owned tables and arrays; the grid archive is closed before return.

    Raises:
        OSError: A result cannot be read.
        ValueError: Seeds are duplicated or inconsistent, grid shapes are incorrect, or a
            quadrant is unsupported.
        KeyError: A required table column or grid array is missing.
    """
    scores_df = pd.read_parquet(data_directory / "factorization_scores.parquet")
    selections_df = pd.read_parquet(data_directory / "selected_examples.parquet")
    selections_df = selections_df.loc[:, ["seed", "quadrant", "target_group_share", "rank"]]

    if scores_df["seed"].duplicated().any():
        raise ValueError("Factorization scores must have one row per seed")

    selected_scores_df = selections_df.merge(
        scores_df.drop(columns="target_group_share"), on="seed", validate="many_to_one", how="left"
    )

    if selected_scores_df["group_share"].isna().any():
        raise ValueError("Selected example seeds are absent from the score table")

    with np.load(data_directory / "grids.npz", allow_pickle=False) as grids:
        seeds = grids["seed"]

        if len(np.unique(seeds)) != len(seeds) or set(seeds) != set(scores_df["seed"]):
            raise ValueError("Grid archive seeds must match the factorization score table")

        seed_positions = {int(seed): index for index, seed in enumerate(seeds)}
        shares = grids["shares"]

        if shares.shape != (len(seeds), GRID_SIDE_LENGTH, GRID_SIDE_LENGTH):
            raise ValueError("Grid archive must contain one 16×16 share grid per seed")

        example_grids = {}

        for seed, quadrant, target_share, rank in selections_df.itertuples(index=False, name=None):
            example = SelectedExample(
                quadrant=FactorQuadrant(quadrant),
                target_group_share=float(target_share),
                rank=int(rank),
                seed=int(seed),
            )

            if example.rank == 1:
                example_grids[example] = shares[seed_positions[example.seed]]

    return FactorizationPlotData(scores_df, selected_scores_df, example_grids)


def build_faded_quadrant_colors(intensity: np.ndarray, layout: np.ndarray) -> np.ndarray:
    """Color intensity/layout quadrants, fading to white near their dividing lines.

    Cut lines are intensity 0.5 and layout 0.2. CIELAB interpolation uses the same smoothstep fade
    strength in both directions, reaching full color at normalized distance 0.22 from a cut line.
    The minimum color strength is 0.12. Inputs are not modified.

    Args:
        intensity (np.ndarray): Finite, one-dimensional intensity values.
        layout (np.ndarray): Aligned finite layout values.

    Returns:
        np.ndarray: One RGB triple per input pair, with components in [0, 1].
    """
    colors = np.empty((len(intensity), 3))

    for mask, quadrant in (
        ((intensity < 0.5) & (layout >= 0.2), FactorQuadrant.WEAK_CLUSTERED),
        ((intensity >= 0.5) & (layout >= 0.2), FactorQuadrant.STRONG_CLUSTERED),
        ((intensity < 0.5) & (layout < 0.2), FactorQuadrant.WEAK_DISPERSED),
        ((intensity >= 0.5) & (layout < 0.2), FactorQuadrant.STRONG_DISPERSED),
    ):
        colors[mask] = to_rgb(QUADRANT_COLORS[quadrant])

    distance = np.minimum(np.abs(intensity - 0.5) / 0.5, np.abs(layout - 0.2) / 0.8)
    position = np.clip(distance / 0.22, 0, 1)
    strength = 0.12 + (1 - 0.12) * position * position * (3 - 2 * position)
    lab_colors = rgb2lab(colors[None])[0]
    white = np.array([100.0, 0, 0])
    faded_lab = white + strength[:, None] * (lab_colors - white)

    return np.clip(lab2rgb(faded_lab[None])[0], 0, 1)


def plot_factorization_gradients(scores_df: pd.DataFrame, output_directory: Path) -> None:
    """Draw the two factor-gradient panel sets and their matching standalone colorbars.

    Args:
        scores_df (pd.DataFrame): Saved scores in their desired drawing order.
        output_directory (Path): Figure root; each gradient gets its own subdirectory.

    Raises:
        OSError: A PNG cannot be written. Each exported figure is closed.
    """
    for factor, cmap, norm in (
        ("intensity", "viridis", PowerNorm(0.5, 0, 1)),
        ("layout", "plasma_r", Normalize(-0.6, 1)),
    ):
        gradient_colors = plt.get_cmap(cmap)(norm(scores_df[factor].to_numpy()))
        plot_factorization_panels(
            scores_df,
            gradient_colors,
            output_directory / f"{factor}_gradient",
            panel_style=FactorizationPanelStyle.GRADIENT,
        )

        ticks = (0, 0.1, 0.25, 0.5, 1) if factor == "intensity" else (-0.6, 0.2, 1)
        _save_factorization_colorbar(
            output_directory / f"{factor}_colorbar", cmap, norm, ticks, 2.736
        )


def plot_factorization_panels(
    scores_df: pd.DataFrame,
    colors: np.ndarray,
    output_directory: Path,
    *,
    panel_style: FactorizationPanelStyle,
    metrics: tuple[str, ...] = SCORE_COLUMNS,
) -> None:
    """Draw a factor-space key and score-versus-share panels using one aligned color array.

    Panels use fixed comparison scales: share [0, .52], intensity [0, 1], and layout [-.6, 1].
    Observations outside these display ranges remain in the saved scores but are clipped here.

    Args:
        scores_df (pd.DataFrame): Saved factors, group_share, and score columns in drawing order.
        colors (np.ndarray): Aligned RGB or RGBA rows. Inputs are not modified.
        output_directory (Path): Destination for the factor key and one PNG per metric.
        panel_style (FactorizationPanelStyle): Select marker appearance, panel proportions, and
            the Capy display range. Gradient panels are shorter and omit the quadrant background.
        metrics (tuple[str, ...]): Score columns to draw; defaults to the eight comparison scores.

    Raises:
        KeyError: A required score column is missing.
        OSError: A PNG cannot be written. Each exported figure is closed.
    """
    if panel_style is FactorizationPanelStyle.GRADIENT:
        score_width, height = 1.287, 2.736
    elif panel_style is FactorizationPanelStyle.EXPOSURE_COMPARISON:
        score_width, height = 1.535, 3.696
    else:
        score_width, height = 1.311, 3.696

    figure, axes = _create_factorization_plot(1.6 * score_width, height)

    if panel_style is not FactorizationPanelStyle.GRADIENT:
        intensity, layout = np.meshgrid(np.linspace(0, 1, 240), np.linspace(-0.6, 1, 240))
        swatch = build_faded_quadrant_colors(intensity.ravel(), layout.ravel())
        axes.imshow(
            swatch.reshape(240, 240, 3),
            origin="lower",
            extent=(0, 1, -0.6, 1),
            aspect="auto",
            alpha=0.3,
            zorder=0,
        )

        axes.axvline(0.5, color="0.4", linewidth=0.7)
        axes.axhline(0.2, color="0.4", linewidth=0.7)
    else:
        axes.axhline(0.2, color="0.5", linewidth=0.5, zorder=0)

    _draw_factorization_points(
        axes, scores_df["intensity"].to_numpy(), scores_df["layout"].to_numpy(), colors, panel_style
    )
    axes.set(
        xlim=(0, 1),
        ylim=(-0.6, 1),
        xticks=[0, 0.5, 1],
        yticks=[-0.6, 0.2, 1],
    )
    save_plot(figure, output_directory / "intensity_vs_layout")

    for metric in metrics:
        figure, axes = _create_factorization_plot(score_width, height)
        _draw_factorization_points(
            axes,
            scores_df["group_share"].to_numpy(),
            scores_df[metric].to_numpy(),
            colors,
            panel_style,
        )
        style_factorization_score(axes, metric, panel_style)
        save_plot(figure, output_directory / metric)


def style_factorization_score(
    axes: Axes, metric: str, panel_style: FactorizationPanelStyle
) -> None:
    """Set score/share limits and add the metric's reference line to existing axes.

    Args:
        axes (Axes): Plot to modify; the caller owns its export and closing.
        metric (str): Score column. Isolation and exposure use the identity reference line;
            Capy uses 0.5. Spatial evenness and Moran use zero; aspatial scores have no line.
        panel_style (FactorizationPanelStyle): Selected targets use Capy limits [.38, .77];
            all-grid and gradient panels use [.2, 1].
    """
    axes.set(xlim=(0, 0.52), xticks=[0, 0.25, 0.5])

    if metric == "capy":
        if panel_style is FactorizationPanelStyle.SELECTED_TARGETS:
            axes.set(ylim=(0.38, 0.77), yticks=[0.4, 0.5, 0.6, 0.7])
        else:
            axes.set(ylim=(0.2, 1), yticks=[0.3, 0.5, 0.7, 0.9])

        axes.axhline(0.5, color="0.6", linewidth=0.5, zorder=0)
    elif metric.startswith("spatial_") or metric == "moran_with_self":
        axes.set(ylim=(-0.6, 1), yticks=[-0.5, 0, 0.5, 1])
        axes.axhline(0, color="0.6", linewidth=0.5, zorder=0)
    elif metric in ("x_isolation", "y_to_x_exposure"):
        axes.set(ylim=(0, 1), yticks=[0, 0.5, 1])
        axes.plot(
            [0, 0.52],
            [0, 0.52],
            color="0.5",
            linewidth=0.8,
            linestyle="--",
            zorder=0,
        )
    else:
        axes.set(ylim=(-0.03, 1.03), yticks=[0, 0.5, 1])


def _create_factorization_plot(width: float, height: float) -> tuple[Figure, Axes]:
    """Create plain, boxed axes with fixed dimensions in inches and compact serif ticks.

    Margins are additional to the requested axes dimensions, keeping marker density consistent
    across separately exported panels. The caller owns export and closing.
    """
    figure_width, figure_height = width + 0.5, height + 0.4

    with plt.rc_context(
        {
            "font.family": "serif",
            "font.serif": ["cmr10"],
            "font.size": 11,
            "mathtext.fontset": "cm",
            "axes.formatter.use_mathtext": True,
        }
    ):
        figure = plt.figure(figsize=(figure_width, figure_height))
        axes = figure.add_axes(
            (0.4 / figure_width, 0.3 / figure_height, width / figure_width, height / figure_height)
        )

    axes.grid(False)
    axes.xaxis.set_major_formatter(FuncFormatter(_format_fraction_tick))
    axes.yaxis.set_major_formatter(FuncFormatter(_format_fraction_tick))

    return figure, axes


def _format_fraction_tick(value: float, position: int | None = None) -> str:
    """Format dimensionless ticks as 0, .25, -.5, or 1 without trailing zeros."""
    label = f"{value:g}"

    if label.startswith("0."):
        return label[1:]

    if value < 0:
        return "$" + label.replace("-0.", "-.", 1) + "$"

    return label


def _draw_factorization_points(
    axes: Axes,
    horizontal_values: np.ndarray,
    vertical_values: np.ndarray,
    colors: np.ndarray,
    panel_style: FactorizationPanelStyle,
) -> None:
    """Draw aligned points with the marker appearance for the selected panel family."""
    if panel_style is FactorizationPanelStyle.SELECTED_TARGETS:
        size, edge_width, opacity = 34, 0.5, None
        edge_color = (0.15, 0.15, 0.15, 0.6)
    elif panel_style is FactorizationPanelStyle.GRADIENT:
        size, edge_width, opacity = 2.5, 0, 0.8
        edge_color = (0, 0, 0, 0)
    else:
        size, edge_width, opacity = 4, 0.2, None
        edge_color = (0.2, 0.2, 0.2, 0.25)

    axes.scatter(
        horizontal_values,
        vertical_values,
        c=colors,
        s=size,
        linewidths=edge_width,
        edgecolors=[edge_color],
        alpha=opacity,
        zorder=3,
    )


def _save_factorization_colorbar(
    output_path: Path, cmap: str, norm: Normalize, ticks: tuple[float, ...], height: float
) -> None:
    """Export a vertical colorbar with a 20:1 height-to-width ratio and close its figure.

    Height is the colored region's size in inches. Tick-label margins do not change the bar's
    width. The normalization is shared with the corresponding scatter panels.
    """
    figure_height = height + 0.4

    with plt.rc_context(
        {
            "font.family": "serif",
            "font.serif": ["cmr10"],
            "font.size": 11,
            "mathtext.fontset": "cm",
            "axes.formatter.use_mathtext": True,
        }
    ):
        figure = plt.figure(figsize=(0.65, figure_height))
        axes = figure.add_axes(
            (0.08 / 0.65, 0.3 / figure_height, height / 20 / 0.65, height / figure_height)
        )

    colorbar = figure.colorbar(ScalarMappable(norm=norm, cmap=cmap), cax=axes)
    colorbar.set_ticks(ticks)
    colorbar.formatter = FuncFormatter(_format_fraction_tick)
    colorbar.update_ticks()
    save_plot(figure, output_path)


def plot_factorization_examples(
    example_grids: dict[SelectedExample, np.ndarray], output_directory: Path
) -> None:
    """Render each selected grid separately with a thin gray border.

    Args:
        example_grids (dict[SelectedExample, np.ndarray]): Rank-one identities and their 16×16
            shares. Arrays are read without modification.
        output_directory (Path): Destination for one PNG per quadrant/share target. Filenames
            identify the group; colored frames belong around groups when assembling the strip.

    Raises:
        OSError: A PNG cannot be written. Each exported figure is closed.
    """
    for example, shares in example_grids.items():
        figure, axes = create_plot()
        axes.imshow(shares, cmap="Greys", vmin=0, vmax=1, interpolation="nearest")
        axes.grid(False)
        axes.set(xticks=[], yticks=[])
        axes.spines[:].set_visible(True)
        axes.spines[:].set_color("0.6")
        axes.spines[:].set_linewidth(0.6)

        share_label = round(100 * example.target_group_share)
        save_plot(figure, output_directory / f"{example.quadrant}_share_{share_label:02d}")


def plot_factorization_groups(
    example_grids: dict[SelectedExample, np.ndarray], output_directory: Path
) -> None:
    """Save four framed two-by-two grid groups and a two-by-two assembly of those groups.

    Args:
        example_grids (dict[SelectedExample, np.ndarray]): Four rank-one share grids per quadrant,
            read without modification. Targets 0.45 and 0.33 form the top row; 0.21 and 0.09 form
            the bottom row. Dictionary order does not affect placement.
        output_directory (Path): Destination for four quadrant PNGs and all_groups_2x2.png.

    Raises:
        ValueError: A quadrant does not contain exactly one grid for each share target.
        OSError: A PNG cannot be written. Figures are closed even if drawing or export fails.
    """
    groups = {}

    for quadrant in QUADRANT_COLORS:
        examples = sorted(
            [
                (example, shares)
                for example, shares in example_grids.items()
                if example.quadrant == quadrant
            ],
            key=lambda item: item[0].target_group_share,
            reverse=True,
        )

        if tuple(example.target_group_share for example, _ in examples) != EXAMPLE_SHARE_TARGETS:
            raise ValueError(f"Expected four distinct share targets for {quadrant}")

        groups[quadrant] = examples

    overview = plt.figure(figsize=(11, 11))

    try:
        overview_layout = overview.add_gridspec(
            2, 2, left=0.035, right=0.965, bottom=0.05, top=0.975, wspace=0.15, hspace=0.19
        )

        for group_index, (quadrant, color) in enumerate(QUADRANT_COLORS.items()):
            figure, axes = plt.subplots(2, 2, figsize=(5.5, 5.5))

            try:
                figure.subplots_adjust(
                    left=0.05, right=0.95, bottom=0.08, top=0.97, wspace=0.06, hspace=0.16
                )
                _draw_factorization_group(figure, list(axes.flat), groups[quadrant], color)
                write_figure_png(figure, output_directory / f"{quadrant}_2x2")
            finally:
                plt.close(figure)

            group_layout = overview_layout[group_index // 2, group_index % 2].subgridspec(
                2, 2, wspace=0.06, hspace=0.16
            )
            group_axes = [
                overview.add_subplot(group_layout[index // 2, index % 2]) for index in range(4)
            ]
            _draw_factorization_group(overview, group_axes, groups[quadrant], color)

        write_figure_png(overview, output_directory / "all_groups_2x2")
    finally:
        plt.close(overview)


def _draw_factorization_group(
    figure: Figure,
    axes: list[Axes],
    examples: list[tuple[SelectedExample, np.ndarray]],
    color: str,
) -> None:
    """Draw four grids in row order and enclose them in a frame matching their quadrant.

    The caller owns the figure. Share labels sit below the grids, inside the colored frame.
    Layout must be fixed before drawing; the frame uses the axes' final figure coordinates.
    """
    for axis, (example, shares) in zip(axes, examples, strict=True):
        axis.imshow(shares, cmap="Greys", vmin=0, vmax=1, interpolation="nearest")
        axis.set(xticks=[], yticks=[])
        axis.spines[:].set_color("0.6")
        axis.spines[:].set_linewidth(0.6)
        axis.text(
            0.03,
            -0.03,
            rf"$\rho\approx${example.target_group_share:.2f}",
            transform=axis.transAxes,
            ha="left",
            va="top",
            fontsize=9,
            color="0.25",
        )

    figure.canvas.draw()
    upper_left = axes[0].get_position()
    lower_right = axes[-1].get_position()
    group_height = upper_left.y1 - lower_right.y0
    pad_x = 0.025 * (lower_right.x1 - upper_left.x0)
    pad_y = 0.025 * group_height
    figure.add_artist(
        Rectangle(
            (upper_left.x0 - pad_x, lower_right.y0 - 2.4 * pad_y),
            lower_right.x1 - upper_left.x0 + 2 * pad_x,
            group_height + 3.4 * pad_y,
            transform=figure.transFigure,
            fill=False,
            edgecolor=color,
            linewidth=5,
        )
    )
