"""Compare national scores with grid configurations."""

from itertools import product
from pathlib import Path

import pandas as pd
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.lines import Line2D
from national_pipeline.assign_study_areas.study_area_columns import (
    StudyAreaColumn,
)
from national_pipeline.compute_metrics.metric_types import (
    MetricColumn,
    MetricName,
    PopulationComparison,
)
from national_pipeline.derived_file_paths import build_study_area_label
from national_pipeline.pipeline_config import PipelineConfig
from plotting.figure_style import (
    GRAY_60,
    METRO_COLORS,
    TEAL,
    create_score_scatter_plot,
    save_legend,
    save_plot,
)
from plotting.grid_references import plot_grid_references

from national_figures.output_names import POPULATION_COMPARISON_LABELS
from national_figures.prepare_grid_vs_national_scores import COMPARISON_METRICS

TOP_10_EDGE_COLOR = "white"


def plot_grid_vs_national_scores(
    config: PipelineConfig, output_directory: Path, data_directory: Path
) -> None:
    """Plot 2020 national scores against grid references for each prepared comparison.

    Args:
        config (PipelineConfig): Study-area type and vintage used in image-set folder names.
        output_directory (Path): National image root.
        data_directory (Path): Prepared tract_scores, reference_scores, and top_10_metros tables.

    Raises:
        OSError: Reading prepared tables or writing PNGs fails.
    """
    scores_df = pd.read_parquet(data_directory / "tract_scores.parquet")
    references_df = pd.read_parquet(data_directory / "reference_scores.parquet")
    top_10_metros_df = pd.read_parquet(data_directory / "top_10_metros.parquet")

    metric_names = [metric for metric in COMPARISON_METRICS if metric in scores_df.columns]
    top_10_ids = top_10_metros_df[StudyAreaColumn.STUDY_AREA_ID]

    for comparison, comparison_df in scores_df.groupby(MetricColumn.COMPARISON):
        population_comparison = PopulationComparison(str(comparison))
        comparison_label = POPULATION_COMPARISON_LABELS[population_comparison]
        image_set_name = f"{comparison_label}_{build_study_area_label(config)}_2020_tract"
        image_directory = output_directory / "grid_vs_national_scores" / image_set_name

        top_10_scores_df = comparison_df.loc[
            comparison_df[StudyAreaColumn.STUDY_AREA_ID].isin(top_10_ids)
        ]
        samples = {"all": comparison_df, "top_10": top_10_scores_df}

        for (sample_name, sample_df), metric in product(samples.items(), metric_names):
            sample_suffix = "_top_10" if sample_name == "top_10" else ""
            figure, axes = create_score_scatter_plot()
            metro_handles, reference_handles = plot_score_by_share(
                axes,
                sample_df,
                references_df,
                top_10_metros_df,
                metric,
                population_comparison,
            )

            save_plot(
                figure, image_directory / f"TRACT_grid_v_nat{sample_suffix}_{metric}_by_share"
            )

            if sample_name == "all" and metric == metric_names[0]:
                save_legend(metro_handles, image_directory / "top_10_legend")
                save_legend(reference_handles, image_directory / "reference_legend")


def plot_score_by_share(
    axes: Axes,
    scores_df: pd.DataFrame,
    references_df: pd.DataFrame,
    top_10_metros_df: pd.DataFrame,
    metric: MetricName,
    comparison: PopulationComparison,
) -> tuple[list[PathCollection], list[Line2D]]:
    """Draw one empirical score against population share with square-lattice references.

    Regular Capy is used for both observations and reference curves. Empirical graph scores
    need not obey regular-lattice bounds; axes expand to retain observed values. White–Black plots
    keep the frame at share 0.5, with larger shares in an unboxed margin.

    Args:
        axes (Axes): Caller-owned axes, left open for further adjustment and export.
        scores_df (pd.DataFrame): One comparison/year/sample of scores and oriented group shares.
        references_df (pd.DataFrame): Analytic arrangement/metric/group_share/value rows.
        top_10_metros_df (pd.DataFrame): study_area_id, name, and metro_code in the fixed metro order.
        metric (MetricName): Score column to draw.
        comparison (PopulationComparison): Determines whether references span the full share
            range.

    Returns:
        tuple[list[PathCollection], list[Line2D]]: Actual metro and reference artists for legends.
    """
    reference_handles = plot_grid_references(
        axes,
        references_df,
        metric,
        full_share_range=comparison == PopulationComparison.WHITE_POC,
    )

    top_10_ids = top_10_metros_df[StudyAreaColumn.STUDY_AREA_ID]
    ordinary_df = scores_df.loc[~scores_df[StudyAreaColumn.STUDY_AREA_ID].isin(top_10_ids)]
    axes.scatter(
        ordinary_df.group_share,
        ordinary_df[metric],
        s=13,
        color=TEAL,
        alpha=0.45,
        edgecolors="none",
        zorder=4,
    )

    metro_handles = []

    for _, metro in top_10_metros_df.iterrows():
        metro_df = scores_df.loc[
            scores_df[StudyAreaColumn.STUDY_AREA_ID].eq(metro[StudyAreaColumn.STUDY_AREA_ID])
        ]

        if metro_df.empty:
            continue

        artist = axes.scatter(
            metro_df.group_share,
            metro_df[metric],
            s=35,
            color=METRO_COLORS.get(metro[StudyAreaColumn.METRO_CODE], GRAY_60),
            edgecolors=TOP_10_EDGE_COLOR,
            linewidths=0.5,
            clip_on=False,
            zorder=5,
            label=str(metro[StudyAreaColumn.NAME]),
        )
        metro_handles.append(artist)

    if comparison == PopulationComparison.WHITE_BLACK:
        axes.set_xlim(0, max(0.53, float(scores_df.group_share.max()) + 0.02))
        axes.spines["right"].set_position(("data", 0.5))
        axes.spines[["top", "bottom"]].set_bounds(0, 0.5)

    finite_values = scores_df[metric].dropna()
    lower, upper = axes.get_ylim()

    if not finite_values.empty:
        axes.set_ylim(
            min(lower, float(finite_values.min())), max(upper, float(finite_values.max()))
        )

    return metro_handles, reference_handles
