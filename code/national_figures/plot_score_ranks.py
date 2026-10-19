"""Draw pairwise comparisons of prepared population-selected score ranks."""

from itertools import combinations
from pathlib import Path
from typing import cast

import pandas as pd
from matplotlib.axes import Axes
from national_pipeline.assign_study_areas.study_area_columns import MembershipColumn
from national_pipeline.compute_metrics.metric_types import (
    MetricColumn,
    MetricName,
    PopulationComparison,
)
from national_pipeline.derived_file_paths import build_study_area_label
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import PipelineConfig
from plotting.figure_style import DENIM, create_plot, save_plot

from national_figures.output_names import POPULATION_COMPARISON_LABELS

RANK_REFERENCE_COLOR = "#333333"


def plot_score_rank_comparisons(
    config: PipelineConfig, output_directory: Path, data_directory: Path
) -> None:
    """Read prepared ranks and export one image per primary-score pair.

    Args:
        config (PipelineConfig): Study-area type and vintage used in the image-set folder name.
        output_directory (Path): National image root.
        data_directory (Path): Folder containing rank_rows.parquet.

    Raises:
        OSError: Reading ranks or writing an image fails.
    """
    ranks_df = pd.read_parquet(data_directory / "rank_rows.parquet")
    metric_names = [
        metric
        for metric in (MetricName.CAPY, MetricName.DISSIMILARITY, MetricName.MORAN_ROW_STANDARDIZED)
        if f"{metric}_rank" in ranks_df.columns
    ]
    selection_columns = [
        MembershipColumn.CENSUS_YEAR,
        MembershipColumn.GEOGRAPHY_LEVEL,
        MetricColumn.COMPARISON,
    ]
    for selection, selection_df in ranks_df.groupby(selection_columns, sort=True):
        year, level, comparison = cast(tuple[int, str, str], selection)
        comparison_label = POPULATION_COMPARISON_LABELS[PopulationComparison(comparison)]
        image_set_name = (
            f"{comparison_label}_{build_study_area_label(config)}_score_rank_comparisons"
        )
        image_directory = output_directory / "score_ranks" / image_set_name
        for x_metric, y_metric in combinations(metric_names, 2):
            figure, axes = create_plot()
            plot_score_rank_pair(axes, selection_df, x_metric, y_metric)
            save_plot(
                figure,
                image_directory
                / f"{year}_{GeographyLevel(level).name.lower()}_{y_metric}_vs_{x_metric}",
            )


def plot_score_rank_pair(
    axes: Axes, ranks_df: pd.DataFrame, x_metric: MetricName, y_metric: MetricName
) -> None:
    """Draw one pair of prepared score ranks and their equal-rank reference line.

    Args:
        axes (Axes): Caller-owned axes, left open for adjustment and export.
        ranks_df (pd.DataFrame): One row per selected area with metric_rank columns.
        x_metric (MetricName): Horizontal rank.
        y_metric (MetricName): Vertical rank.
    """
    axes.scatter(
        ranks_df[f"{x_metric}_rank"],
        ranks_df[f"{y_metric}_rank"],
        s=8,
        color=DENIM,
        linewidths=0,
        zorder=2,
    )
    axes.plot(
        [1, len(ranks_df)], [1, len(ranks_df)], color=RANK_REFERENCE_COLOR, linewidth=0.7, alpha=0.7
    )
    axes.set_box_aspect(1)
