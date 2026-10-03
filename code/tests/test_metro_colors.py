"""Metro colors follow identities across figure families and selected rankings."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from experiments.grid_configurations.grid_reference_scores import build_grid_reference_scores
from matplotlib.colors import to_rgba
from national_figures import plot_grid_vs_national_scores, plot_national_results
from national_pipeline.compute_metrics.metric_types import MetricName, PopulationComparison
from national_pipeline.geography_types import MetroCode, StudyAreaType
from national_pipeline.pipeline_config import PipelineConfig
from plotting.figure_style import APPLE_GREEN, DENIM, GRAY_60, TEAL


@pytest.mark.parametrize(
    "area_type", [StudyAreaType.CBSA, StudyAreaType.MAX_CITY, StudyAreaType.MAX_COUNTY]
)
@pytest.mark.parametrize(
    "selected_codes",
    [
        [MetroCode.NEW_YORK, MetroCode.LOS_ANGELES, MetroCode.PHOENIX],
        [MetroCode.PHOENIX, MetroCode.LOS_ANGELES, MetroCode.NEW_YORK],
        [MetroCode.LOS_ANGELES, "99999"],
    ],
)
def test_history_and_scatter_colors_follow_metros_across_rankings(area_type, selected_codes):
    top_10_df = pd.DataFrame(
        {
            "study_area_id": [f"{area_type}_{code}" for code in selected_codes],
            "metro_code": selected_codes,
            "name": selected_codes,
        }
    )
    scores_df = top_10_df.assign(
        census_year=2020,
        geography_level="tracts",
        metric=MetricName.CAPY,
        value=0.6,
        capy=0.6,
        group_share=0.3,
    )
    original_top_10_df = top_10_df.copy(deep=True)
    expected_colors = {
        MetroCode.NEW_YORK: DENIM,
        MetroCode.LOS_ANGELES: APPLE_GREEN,
        MetroCode.PHOENIX: TEAL,
        "99999": GRAY_60,
    }
    figure, (history_axes, scatter_axes) = plt.subplots(1, 2)

    try:
        history_lines, _ = plot_national_results.plot_score_history(
            history_axes,
            scores_df,
            top_10_df,
            PipelineConfig(study_area_type=area_type, census_geography_years=(2020,)),
        )
        scatter_points, _ = plot_grid_vs_national_scores.plot_score_by_share(
            scatter_axes,
            scores_df,
            build_grid_reference_scores(),
            top_10_df,
            MetricName.CAPY,
            PopulationComparison.WHITE_BLACK,
        )
        for code, line, points in zip(selected_codes, history_lines, scatter_points, strict=True):
            assert line.get_color() == expected_colors[code]
            np.testing.assert_allclose(points.get_facecolors(), [to_rgba(expected_colors[code])])
        pd.testing.assert_frame_equal(top_10_df, original_top_10_df)
    finally:
        plt.close(figure)
