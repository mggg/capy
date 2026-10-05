"""Separate plot exports for figures assembled and annotated in LaTeX."""

from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Colormap, LinearSegmentedColormap, Normalize, to_hex
from matplotlib.figure import Figure
from national_pipeline.geography_types import MetroCode

# Names and exact hex values from GerryTools' LaTeX color table.
TEAL = "#008080"
BYZANTINE = "#BD33A4"
DENIM = "#1560bd"
APPLE_GREEN = "#8db600"
CHERRY_BLOSSOM_PINK = "#ffb7c5"
DARK_TANGERINE = "#ffa812"
CADMIUM_GREEN = "#006b3c"
PURPLE_HEART = "#69359c"
ALIZARIN = "#d11a42"
BLACK = "#000000"
GOLDEN_YELLOW = "#FFCC00"
VERMILION = "#E32636"

# These exact shades are outside GerryTools' LaTeX color table.
CHINESE_GOLD = "#CC9900"
AMBER = "#ffbf00"
OKABE_ITO_SKY_BLUE = "#56b4e9"
GRAY_60 = "#999999"  # 60% white.

DEMOGRAPHIC_COLORS = {"constant": TEAL, "growth": BYZANTINE, "decline": CHINESE_GOLD}
DIFFUSION_DEMOGRAPHIC_COLORS = {"constant": TEAL, "growth": BYZANTINE, "decline": GOLDEN_YELLOW}
MORAN_COLORS = {"moran_with_self": BLACK, "moran_row_standardized": VERMILION}


AREA_COLORS = (
    DENIM,
    APPLE_GREEN,
    CHERRY_BLOSSOM_PINK,
    DARK_TANGERINE,
    CADMIUM_GREEN,
    PURPLE_HEART,
    ALIZARIN,
    OKABE_ITO_SKY_BLUE,
    BLACK,
    GRAY_60,
)


# Metro identities keep their colors across rankings, vintages, and selected subsets.
METRO_COLORS = {
    MetroCode.NEW_YORK: DENIM,
    MetroCode.LOS_ANGELES: APPLE_GREEN,
    MetroCode.CHICAGO: CHERRY_BLOSSOM_PINK,
    MetroCode.DALLAS: DARK_TANGERINE,
    MetroCode.HOUSTON: CADMIUM_GREEN,
    MetroCode.WASHINGTON: PURPLE_HEART,
    MetroCode.PHILADELPHIA: ALIZARIN,
    MetroCode.MIAMI: OKABE_ITO_SKY_BLUE,
    MetroCode.ATLANTA: BLACK,
    MetroCode.BOSTON: GRAY_60,
    MetroCode.PHOENIX: TEAL,
    MetroCode.SAN_ANTONIO: BYZANTINE,
    MetroCode.SAN_DIEGO: CHINESE_GOLD,
    MetroCode.SAN_JOSE: GOLDEN_YELLOW,
}


TICK_COLOR = "#333333"
PLOT_GRID_COLOR = "#eae8e0"
TRACE_GRID_COLOR = "#dddddd"
INDIVIDUAL_METRO_COLOR_FOR_HISTORIES = "#7cb3f6"
UNAVAILABLE_YEAR_COLOR = "lightgray"


# None keeps the fixed year palette; use AMBER, PURPLE_HEART, DENIM, or a color string for shades.
YEAR_BASE_COLOR: str | None = None

# Fixed colors for each census year.
YEAR_COLORS = {
    1980: DENIM,
    1990: CADMIUM_GREEN,
    2000: APPLE_GREEN,
    2010: AMBER,
    2020: ALIZARIN,
}

if YEAR_BASE_COLOR is not None:
    # Blend through the base color, omitting pure black and white at the endpoints.
    year_cmap = LinearSegmentedColormap.from_list("years", ["black", YEAR_BASE_COLOR, "white"])
    year_shades = [
        to_hex(color) for color in year_cmap(np.linspace(0, 1, len(YEAR_COLORS) + 2))[1:-1]
    ]
    YEAR_COLORS = dict(zip(YEAR_COLORS, year_shades, strict=True))


def create_plot() -> tuple[Figure, Axes]:
    """Create a plot with serif ticks, a light grid, and no bounding box."""
    with plt.rc_context({"font.family": "serif", "font.size": 9}):
        figure, axes = plt.subplots(figsize=(3.4, 3.4), layout="constrained")

    axes.spines[:].set_visible(False)
    axes.tick_params(length=0, colors=TICK_COLOR)
    axes.set_axisbelow(True)
    axes.grid(color=PLOT_GRID_COLOR, linewidth=0.6)

    return figure, axes


def save_plot(figure: Figure, output_path: Path) -> None:
    """Save one plot as a 300 dpi PNG without titles, axis labels, or an embedded legend.

    Args:
        figure (Figure): Exactly one axes, closed after export. Numeric ticks are retained.
        output_path (Path): Destination stem; its parent is created if necessary.

    Raises:
        ValueError: The figure contains multiple plots or a figure-level legend.
        OSError: The PNG cannot be written.
    """
    if len(figure.axes) != 1 or figure.legends:
        raise ValueError("Export each plot and legend as a separate figure")

    axes = figure.axes[0]
    axes.set(xlabel="", ylabel="", title="")
    axes.set_title("", loc="left")
    axes.set_title("", loc="right")

    legend = axes.get_legend()

    if legend is not None:
        legend.remove()

    figure.suptitle("")

    write_figure_png(figure, output_path)


def save_colorbar(output_path: Path, cmap: str | Colormap, minimum: float, maximum: float) -> None:
    """Export an independent vertical colorbar with numeric ticks and no label."""
    figure = plt.figure(figsize=(0.8, 3.4), layout="constrained")
    axes = figure.add_subplot()
    figure.colorbar(
        ScalarMappable(norm=Normalize(minimum, maximum), cmap=cmap),
        cax=axes,
    )
    save_plot(figure, output_path)


def save_legend(handles: Sequence[Artist], output_path: Path) -> None:
    """Save a separate legend matching the supplied artists, with a 0.04-inch margin.

    Args:
        handles (Sequence[Artist]): Labeled lines or scatter points copied into the legend.
            Their source figures can already be closed.
        output_path (Path): Destination stem for the 300 dpi PNG.

    Raises:
        OSError: The PNG cannot be written.
    """
    figure = plt.figure()
    legend = figure.legend(
        handles=handles,
        loc="center",
        frameon=False,
        borderpad=0,
        prop={"family": "serif", "size": 9},
    )
    figure.canvas.draw()
    legend_bounds = legend.get_window_extent().transformed(figure.dpi_scale_trans.inverted())
    figure.set_size_inches(legend_bounds.width + 0.08, legend_bounds.height + 0.08)

    write_figure_png(figure, output_path)


def write_figure_png(figure: Figure, output_path: Path) -> None:
    """Write a 300 dpi PNG and close its figure even if export fails."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        figure.savefig(output_path.with_suffix(".png"), dpi=300)
    finally:
        plt.close(figure)


def create_trace_plot() -> tuple[Figure, Axes]:
    """Create a diffusion or score-history plot with left/bottom axes and a light gray grid."""
    with plt.rc_context({"font.family": "sans-serif", "font.size": 9}):
        figure, axes = plt.subplots(figsize=(3.6, 3.1), layout="constrained")

    axes.spines[["top", "right"]].set_visible(False)
    axes.grid(color=TRACE_GRID_COLOR, linewidth=0.7)
    axes.set_axisbelow(True)

    return figure, axes


def create_score_scatter_plot() -> tuple[Figure, Axes]:
    """Create serif axes for scores plotted against population share."""
    with plt.rc_context({"font.family": "serif", "font.size": 10}):
        figure, axes = plt.subplots(figsize=(2.8, 3.3), layout="constrained")

    return figure, axes
