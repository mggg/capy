"""Draw national histories and comparisons from prepared figure tables."""

from pathlib import Path

import pandas as pd
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from national_pipeline.assign_study_areas.study_area_columns import (
    MembershipColumn,
    StudyAreaColumn,
)
from national_pipeline.compute_metrics.metric_types import (
    MetricColumn,
    MetricName,
)
from national_pipeline.derived_file_paths import build_study_area_label
from national_pipeline.geography_types import GeographyLevel, StudyAreaType
from national_pipeline.pipeline_config import PipelineConfig
from plotting.figure_style import (
    AREA_COLORS,
    DENIM,
    GRAY_60,
    INDIVIDUAL_METRO_COLOR_FOR_HISTORIES,
    METRO_COLORS,
    PLOT_GRID_COLOR,
    UNAVAILABLE_YEAR_COLOR,
    create_plot,
    save_legend,
    save_plot,
)

from national_figures.output_names import POPULATION_COMPARISON_LABELS

# Unspecified years use their full numeric labels; an empty string hides one year's label.
HISTORY_X_TICK_LABELS: dict[int, str] = {}
HISTORY_SHOW_X_TICK_LABELS = True

# Edit these tick locations independently of the limits below.
HISTORY_Y_TICKS = {
    MetricName.MORAN_ROW_STANDARDIZED: [-0.5, 0, 0.5, 1],
    MetricName.DISSIMILARITY: [0.25, 0.5, 0.75, 1],
    MetricName.CAPY: [0.45, 0.6, 0.75, 0.9],
    MetricName.ENTROPY_INDEX: [0, 0.25, 0.5, 0.75, 1],
    MetricName.RELATIVE_DIVERSITY: [0, 0.25, 0.5, 0.75, 1],
    MetricName.ASPATIAL_CAPY: [0.5, 0.6, 0.7, 0.8, 0.9, 1],
    MetricName.SPATIAL_DISSIMILARITY: [0, 0.25, 0.5, 0.75, 1],
    MetricName.SPATIAL_ENTROPY_INDEX: [0, 0.25, 0.5, 0.75, 1],
    MetricName.SPATIAL_RELATIVE_DIVERSITY: [0, 0.25, 0.5, 0.75, 1],
    MetricName.MORAN_WITH_SELF: [-0.5, 0, 0.5, 1],
}

# Horizontal grid positions are independent of ticks; [] hides a metric's horizontal grid.
# These settings do not change plot limits.
HISTORY_Y_GRID_LINES = {
    MetricName.MORAN_ROW_STANDARDIZED: [-0.5, 0, 0.5, 1],
    MetricName.DISSIMILARITY: [0, 0.25, 0.5, 0.75, 1],
    MetricName.CAPY: [0.45, 0.6, 0.75, 0.9],
    MetricName.ENTROPY_INDEX: [0, 0.25, 0.5, 0.75, 1],
    MetricName.RELATIVE_DIVERSITY: [0, 0.25, 0.5, 0.75, 1],
    MetricName.ASPATIAL_CAPY: [0.5, 0.6, 0.7, 0.8, 0.9, 1],
    MetricName.SPATIAL_DISSIMILARITY: [0, 0.25, 0.5, 0.75, 1],
    MetricName.SPATIAL_ENTROPY_INDEX: [0, 0.25, 0.5, 0.75, 1],
    MetricName.SPATIAL_RELATIVE_DIVERSITY: [0, 0.25, 0.5, 0.75, 1],
    MetricName.MORAN_WITH_SELF: [-0.5, 0, 0.5, 1],
}
# Metrics without fixed limits retain the limits set by their data and ticks.
HISTORY_Y_LIMITS = {MetricName.ENTROPY_INDEX: (0, 1)}

HISTORY_Y_GRID_COLOR = PLOT_GRID_COLOR
HISTORY_Y_GRID_LINEWIDTH = 0.6  # Points.


def plot_national_figures(
    config: PipelineConfig, output_directory: Path, data_directory: Path
) -> None:
    """Read prepared histories and save each metric's combined plot and separate legends.

    Args:
        config (PipelineConfig): Study-area type/vintage for folders and years for the display axis.
        output_directory (Path): National figure root; history runs go under its history/ folder.
        data_directory (Path): Prepared national figure tables.

    Raises:
        OSError: An input cannot be read or an output cannot be written.
    """
    histories_df = pd.read_parquet(data_directory / "trajectory_rows.parquet")
    top_10_metros_df = pd.read_parquet(data_directory / "top_10_metros.parquet")
    study_area_label = build_study_area_label(config)

    for _, selected_df in histories_df.groupby(
        [MetricColumn.COMPARISON, MembershipColumn.GEOGRAPHY_LEVEL], sort=False
    ):
        comparison = selected_df[MetricColumn.COMPARISON].iloc[0]
        level = GeographyLevel(selected_df[MembershipColumn.GEOGRAPHY_LEVEL].iloc[0])
        geography_name = level.name.lower()

        history_directory = (
            output_directory
            / "history"
            / (
                f"{POPULATION_COMPARISON_LABELS[comparison]}_{study_area_label}_{geography_name}_histories"
            )
        )

        top_10_handles: list[Line2D] = []
        individual_and_mean_handles: list[Line2D] = []

        for metric, complete_df in selected_df.groupby(MetricColumn.METRIC, sort=False):
            figure, axes = create_plot()
            top_10_handles, individual_and_mean_handles = plot_score_history(
                axes, complete_df, top_10_metros_df, config
            )

            save_plot(
                figure, history_directory / f"{geography_name.upper()}_{metric}_histories.png"
            )

        save_legend(top_10_handles, history_directory / "top_10_legend")
        save_legend(individual_and_mean_handles, history_directory / "individual_metro_legend")


def plot_score_history(
    axes: Axes,
    scores_df: pd.DataFrame,
    top_10_metros_df: pd.DataFrame,
    config: PipelineConfig,
) -> tuple[list[Line2D], list[Line2D]]:
    """Draw one metric's histories, arithmetic mean, top ten, and axis settings on supplied axes.

    Args:
        axes (Axes): Caller-owned axes, left open for further adjustments.
        scores_df (pd.DataFrame): One comparison, geography level, and metric; complete histories
            sorted by area and year.
        top_10_metros_df (pd.DataFrame): Top-ten identities, names, and metro_code in population order.
        config (PipelineConfig): Display years and study-area type for legend wording.

    Returns:
        tuple[list[Line2D], list[Line2D]]: First list: top-ten lines in population order.
            Second list: one individual-area line and the mean line. Both lists can be passed
            directly to save_legend().

    Raises:
        ValueError: No complete score histories are available.
    """
    if scores_df.empty:
        raise ValueError("No complete score histories are available")

    metric = MetricName(scores_df[MetricColumn.METRIC].iloc[0])
    level = GeographyLevel(scores_df[MembershipColumn.GEOGRAPHY_LEVEL].iloc[0])
    display_years = sorted(set(config.census_geography_years))
    area_label, areas_label = (
        ("county", "counties")
        if config.study_area_type == StudyAreaType.COUNTY
        else ("metro", "metros")
    )
    if config.study_area_type == StudyAreaType.COUNTY:
        colors = list(AREA_COLORS[: len(top_10_metros_df)])
    else:
        # Unlisted metros use the same neutral color in every figure.
        colors = [
            METRO_COLORS.get(metro.get(StudyAreaColumn.METRO_CODE), GRAY_60)
            for _, metro in top_10_metros_df.iterrows()
        ]

    top_10_metros_df = top_10_metros_df.assign(color=colors)

    history_lines = []

    for _, history_df in scores_df.groupby(StudyAreaColumn.STUDY_AREA_ID, sort=True):
        line = axes.plot(
            history_df[MembershipColumn.CENSUS_YEAR],
            history_df[MetricColumn.VALUE],
            color=INDIVIDUAL_METRO_COLOR_FOR_HISTORIES,
            linewidth=0.5,
            alpha=0.4,
            marker=None,
            markersize=2.7,
            zorder=1,
            label=f"Individual {area_label}",
        )[0]
        history_lines.append(line)

    means = scores_df.groupby(MembershipColumn.CENSUS_YEAR)[MetricColumn.VALUE].mean()
    mean_line = axes.plot(
        means.index,
        means,
        color=DENIM,
        linewidth=1.7,
        marker="^",
        markersize=3.5,
        zorder=3,
        label=f"Mean across {areas_label}",
    )[0]

    top_10_lines_by_area = {}

    for _, metro in top_10_metros_df.sort_values(StudyAreaColumn.STUDY_AREA_ID).iterrows():
        area_id = metro[StudyAreaColumn.STUDY_AREA_ID]
        history_df = scores_df.loc[scores_df[StudyAreaColumn.STUDY_AREA_ID].eq(area_id)]
        top_10_lines_by_area[area_id] = axes.plot(
            history_df[MembershipColumn.CENSUS_YEAR],
            history_df[MetricColumn.VALUE],
            color=metro["color"],
            linewidth=1.3,
            alpha=0.8,
            marker="o",
            markersize=2.7,
            zorder=2,
            label=str(metro[StudyAreaColumn.NAME]),
        )[0]

    axes.set_xticks(
        display_years, labels=[HISTORY_X_TICK_LABELS.get(year, str(year)) for year in display_years]
    )
    axes.tick_params(axis="x", labelbottom=HISTORY_SHOW_X_TICK_LABELS)
    axes.set_yticks(HISTORY_Y_TICKS[metric])
    y_limits = HISTORY_Y_LIMITS.get(metric, axes.get_ylim())
    axes.grid(False, axis="y", which="both")

    for grid_value in HISTORY_Y_GRID_LINES[metric]:
        axes.axhline(
            grid_value, color=HISTORY_Y_GRID_COLOR, linewidth=HISTORY_Y_GRID_LINEWIDTH, zorder=0
        )

    axes.set_ylim(y_limits)

    if 1980 in display_years and level in (GeographyLevel.BLOCK_GROUP, GeographyLevel.BLOCK):
        axes.axvspan(1980, 1990, color=UNAVAILABLE_YEAR_COLOR, alpha=0.3, zorder=0)

    axes.set_xlim(display_years[0] - 2, display_years[-1] + 2)
    top_10_handles = [
        top_10_lines_by_area[area_id] for area_id in top_10_metros_df[StudyAreaColumn.STUDY_AREA_ID]
    ]

    return top_10_handles, [history_lines[0], mean_line]
