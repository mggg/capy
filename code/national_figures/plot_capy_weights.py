"""Compare Capy ranks under unit, zero, and limiting neighbor weights."""

from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
from national_pipeline.assign_study_areas.study_area_columns import (
    MembershipColumn,
    StudyAreaColumn,
)
from national_pipeline.compute_metrics.metric_types import MetricColumn, PopulationComparison
from national_pipeline.derived_file_paths import build_study_area_label
from national_pipeline.geography_types import GeographyLevel, StudyAreaType
from national_pipeline.pipeline_config import PipelineConfig
from plotting.figure_style import ALIZARIN, DENIM, create_plot, save_legend, save_plot

from national_figures.output_names import POPULATION_COMPARISON_LABELS

RANK_REFERENCE_COLOR = "black"


def plot_capy_weight_comparison(
    config: PipelineConfig, output_directory: Path, data_directory: Path
) -> None:
    """Compare zero and limiting neighbor weights against unit-weight Capy ranks for CBSA tracts.

    Red points show zero neighbor weight and blue points the infinite-weight limit in
    W = I + λA, where λ weights neighbors. Saved rows for other geography levels are ignored.

    Args:
        config (PipelineConfig): Must select CBSAs and include tracts; vintage labels the outputs.
        output_directory (Path): National image root; plots and a shared legend go in capy_weights/.
        data_directory (Path): Folder containing completed capy_weights.parquet scores.

    Raises:
        OSError: Reading scores or writing a component fails.
        ValueError: The configuration does not select CBSA tracts, or tract scores are missing,
            repeated, or nonfinite.
    """
    if (
        config.study_area_type != StudyAreaType.CBSA
        or GeographyLevel.TRACT not in config.census_geography_levels
    ):
        raise ValueError("Capy-weight comparisons require CBSAs with tracts selected")

    scores_df = pd.read_parquet(data_directory / "capy_weights.parquet")
    scores_df = scores_df.loc[scores_df[MembershipColumn.GEOGRAPHY_LEVEL].eq(GeographyLevel.TRACT)]

    if (
        scores_df.empty
        or scores_df.duplicated(
            [
                MembershipColumn.CENSUS_YEAR,
                MembershipColumn.GEOGRAPHY_LEVEL,
                MetricColumn.COMPARISON,
                StudyAreaColumn.STUDY_AREA_ID,
            ]
        ).any()
        or not np.isfinite(scores_df[["zero_rank", "unit_rank", "limit_rank"]].to_numpy()).all()
    ):
        raise ValueError("Capy rank comparison requires one finite score per selected metro")

    image_directory = output_directory / "capy_weights"
    study_area_label = build_study_area_label(config)
    legend_saved = False

    for selection, comparison_df in scores_df.groupby(
        [MembershipColumn.CENSUS_YEAR, MetricColumn.COMPARISON],
        sort=False,
    ):
        year, comparison = cast(tuple[int, str], selection)
        comparison_label = POPULATION_COMPARISON_LABELS[PopulationComparison(comparison)]
        image_name = f"{comparison_label}_{study_area_label}_{year}_tract_capy_neighbor_weights"
        figure, axes = create_plot()

        axes.grid(False)
        axes.spines[["top", "right", "left", "bottom"]].set_visible(True)
        axes.tick_params(length=3)

        handles = []
        for alternative, color, label in (("zero", ALIZARIN, "λ = 0"), ("limit", DENIM, "λ → ∞")):
            artist = axes.scatter(
                comparison_df["unit_rank"],
                comparison_df[f"{alternative}_rank"],
                color=color,
                s=5,
                alpha=0.7,
                linewidths=0,
                zorder=2,
                label=label,
            )
            handles.append(artist)

        axes.plot(
            [1, len(comparison_df)],
            [1, len(comparison_df)],
            color=RANK_REFERENCE_COLOR,
            linestyle="-",
            linewidth=0.7,
        )
        axes.set_box_aspect(1)

        save_plot(figure, image_directory / image_name)

        if not legend_saved:
            save_legend(handles, image_directory / "neighbor_weights_legend")
            legend_saved = True
