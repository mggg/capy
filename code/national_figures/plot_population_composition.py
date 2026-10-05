"""Draw prepared population shares and fitted score relationships."""

from pathlib import Path
from typing import cast

import matplotlib.patheffects as path_effects
import numpy as np
import pandas as pd
from national_pipeline.assign_study_areas.study_area_columns import MembershipColumn
from national_pipeline.compute_metrics.metric_types import MetricColumn
from national_pipeline.derived_file_paths import build_study_area_label
from national_pipeline.pipeline_config import PipelineConfig
from plotting.figure_style import YEAR_COLORS, create_plot, save_legend, save_plot


def plot_population_composition(
    config: PipelineConfig, output_directory: Path, data_directory: Path
) -> None:
    """Read prepared composition tables and save one image per score plus a separate legend.

    Args:
        config (PipelineConfig): Study-area type and vintage used in the image-set folder name.
        output_directory (Path): National image root.
        data_directory (Path): Folder containing composition_rows and composition_fits Parquets.

    Raises:
        OSError: Reading prepared inputs or writing PNGs fails.
    """
    scores_df = pd.read_parquet(data_directory / "composition_rows.parquet")
    fits_df = pd.read_parquet(data_directory / "composition_fits.parquet")
    image_set_name = f"WB_{build_study_area_label(config)}_tract_population_composition"
    image_directory = output_directory / "population_composition" / image_set_name

    for metric, metric_scores_df in scores_df.groupby(MetricColumn.METRIC, sort=False):
        metric_fits_df = fits_df.loc[fits_df[MetricColumn.METRIC].eq(metric)]

        figure, axes = create_plot()

        shuffled_df = metric_scores_df.sample(frac=1, random_state=42)
        axes.scatter(
            shuffled_df["rho"],
            shuffled_df[MetricColumn.VALUE],
            c=[YEAR_COLORS[year] for year in shuffled_df[MembershipColumn.CENSUS_YEAR]],
            s=5,
            linewidths=0,
            zorder=2,
        )

        handles = []
        for year, yearly_fit_df in metric_fits_df.groupby(MembershipColumn.CENSUS_YEAR, sort=True):
            slope, intercept = np.polyfit(
                yearly_fit_df["rho"], yearly_fit_df[MetricColumn.VALUE], 1
            )
            x_points = [0, 0.5]
            y_points = [intercept, slope * 0.5 + intercept]

            (line,) = axes.plot(
                x_points,
                y_points,
                color=YEAR_COLORS[cast(int, year)],
                linewidth=2,
                label=str(year),
                zorder=3,
                path_effects=[
                    path_effects.Stroke(linewidth=2.8, foreground="white"),
                    path_effects.Normal(),
                ],
            )
            handles.append(line)

        minimum_line = axes.axhline(
            float(metric_scores_df[MetricColumn.VALUE].min()),
            color="black",
            linestyle="--",
            linewidth=0.8,
            label="Observed minimum",
        )
        handles.append(minimum_line)

        save_plot(figure, image_directory / f"{metric}_by_black_share")
        save_legend(handles, image_directory / "census_years_legend")
