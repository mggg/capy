"""Draw prepared White–Black entropy histories at geographic resolutions."""

from pathlib import Path

import pandas as pd
from matplotlib.ticker import FormatStrFormatter
from national_pipeline.assign_study_areas.study_area_columns import MembershipColumn
from national_pipeline.derived_file_paths import build_study_area_label
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import PipelineConfig
from plotting.figure_style import create_plot, save_legend, save_plot

from national_figures.plot_national_results import plot_score_history


def plot_entropy_by_geography(
    config: PipelineConfig, output_directory: Path, data_directory: Path
) -> None:
    """Export separate entropy histories and legends from prepared tables.

    Args:
        config (PipelineConfig): Study-area names and selected years for the display axis.
        output_directory (Path): National image root.
        data_directory (Path): Prepared entropy_histories and top_10_metros Parquets.

    Raises:
        OSError: Reading tables or writing PNGs fails.
    """
    histories_df = pd.read_parquet(data_directory / "entropy_histories.parquet")
    top_10_metros_df = pd.read_parquet(data_directory / "top_10_metros.parquet")
    image_set_name = f"WB_{build_study_area_label(config)}_entropy_by_geography"
    image_directory = output_directory / "entropy_by_geography" / image_set_name

    for level, level_df in histories_df.groupby(MembershipColumn.GEOGRAPHY_LEVEL, sort=False):
        figure, axes = create_plot()
        figure.set_layout_engine(None)
        axes.set_position((0.16, 0.16, 0.82, 0.82))

        metro_handles, cohort_handles = plot_score_history(axes, level_df, top_10_metros_df, config)
        axes.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))

        save_plot(
            figure, image_directory / f"{GeographyLevel(level).name.lower()}_entropy_histories"
        )
        save_legend(metro_handles, image_directory / "top_10_metros_legend")
        save_legend(cohort_handles, image_directory / "individuals_and_mean_legend")
