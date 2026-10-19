"""Draw square-lattice score references against population share."""

import pandas as pd
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from plotting.figure_style import BYZANTINE, GOLDEN_YELLOW, TEAL, VERMILION

ARRANGEMENT_STYLES: dict[str, tuple[str, str]] = {
    "cluster": (TEAL, "-"),
    "constant": (GOLDEN_YELLOW, "-"),
    "isolated": (BYZANTINE, "-"),
    "checkerboard": (VERMILION, "-"),
}


REFERENCE_REGION_COLOR = "#dddddd"


def plot_grid_references(
    axes: Axes, reference_scores_df: pd.DataFrame, metric: str, *, full_share_range: bool = False
) -> list[Line2D]:
    """Draw one score's lattice references, preserving coincident values without offsets.

    Gray shading is a regular-lattice reference region, not an empirical feasibility claim.

    Args:
        axes (Axes): Caller-owned axes to draw on; left open for further adjustments.
        reference_scores_df (pd.DataFrame): Analytic arrangement/metric/group_share/value rows.
        metric (str): Score convention in the reference table.
        full_share_range (bool): Mirror symmetric references about 0.5 for oriented shares. Defaults to False, displaying minority shares from zero to one half.

    Returns:
        list[Line2D]: Labeled reference curves for a separate legend.

    Raises:
        ValueError: The requested metric has no reference curves.
    """
    selected_df = reference_scores_df.loc[reference_scores_df.metric.eq(metric)].copy()

    if selected_df.empty:
        raise ValueError(f"No grid reference curves for {metric}")

    if full_share_range:
        mirrored_df = selected_df.loc[selected_df.group_share.lt(0.5)].copy()
        mirrored_df["group_share"] = 1 - mirrored_df.group_share
        selected_df = pd.concat([selected_df, mirrored_df], ignore_index=True)

    spatial = metric.startswith(("spatial_", "moran_"))
    axes.set_xlim(0, 1 if full_share_range else 0.5)
    axes.set_ylim(-1 if spatial else 0, 1)
    axes.set_xticks([0, 0.5, 1] if full_share_range else [0, 0.25, 0.5])
    axes.set_yticks([-1, 0, 1] if spatial else [0, 0.5, 1])

    for spine in axes.spines.values():
        spine.set_linewidth(2)
        spine.set_zorder(1)

    if metric == "capy":
        checker_df = selected_df.loc[selected_df.arrangement.eq("checkerboard")]
        checker_df = checker_df.sort_values("group_share")
        axes.fill_between(
            checker_df.group_share, checker_df.value, 1, color=REFERENCE_REGION_COLOR, zorder=0
        )
    else:
        lower_reference = {
            "aspatial_capy": 0.5,
            "moran_with_self": -0.6,
            "moran_row_standardized": -1,
        }.get(metric, 0)
        axes.fill_between(
            [0, 1 if full_share_range else 0.5],
            lower_reference,
            1,
            color=REFERENCE_REGION_COLOR,
            zorder=0,
        )

    reference_lines = []

    for arrangement, (color, style) in ARRANGEMENT_STYLES.items():
        arrangement_df = selected_df.loc[selected_df.arrangement.eq(arrangement)]
        arrangement_df = arrangement_df.sort_values("group_share")
        (reference_line,) = axes.plot(
            arrangement_df.group_share,
            arrangement_df.value,
            color=color,
            label=arrangement.replace("_", " "),
            linestyle=style,
            linewidth=2.3,
            clip_on=False,
            zorder=3,
        )
        reference_lines.append(reference_line)

    return reference_lines
