"""Score scatter frames distinguish lattice references from observations beyond one-half share."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from experiments.grid_configurations.grid_reference_scores import build_grid_reference_scores
from matplotlib.collections import PolyCollection
from matplotlib.colors import to_rgba
from national_figures.plot_grid_vs_national_scores import plot_score_by_share
from national_pipeline.compute_metrics.metric_types import MetricName, PopulationComparison
from national_pipeline.geography_types import MetroCode
from plotting.figure_style import APPLE_GREEN, create_score_scatter_plot


@pytest.mark.parametrize("comparison", list(PopulationComparison))
@pytest.mark.parametrize("largest_share", [0.4, 0.561])
@pytest.mark.parametrize("metric", [MetricName.CAPY, MetricName.DISSIMILARITY])
def test_scatter_keeps_half_share_frame_and_retains_observations(comparison, largest_share, metric):
    scores_df = pd.DataFrame(
        {
            "study_area_id": ["ordinary", "top"],
            "group_share": [largest_share, 0.3],
            metric: [0.6, 0.7],
        }
    )
    original_df = scores_df.copy(deep=True)
    top_10_df = pd.DataFrame(
        {"study_area_id": ["top"], "name": ["Los Angeles"], "metro_code": [MetroCode.LOS_ANGELES]}
    )
    references_df = build_grid_reference_scores(np.array([0.1, 0.25, 0.5]))
    figure, axes = create_score_scatter_plot()

    try:
        metro_handles, _ = plot_score_by_share(
            axes, scores_df, references_df, top_10_df, metric, comparison
        )
        figure.canvas.draw()
        shading = [artist for artist in axes.collections if isinstance(artist, PolyCollection)]
        shading_max = max(
            path.vertices[:, 0].max() for artist in shading for path in artist.get_paths()
        )

        if comparison == PopulationComparison.WHITE_BLACK:
            assert axes.get_xlim() == pytest.approx((0, max(0.53, largest_share + 0.02)))
            assert axes.spines["right"].get_position() == ("data", 0.5)
            assert axes.spines["top"].get_bounds() == (0, 0.5)
            assert axes.spines["bottom"].get_bounds() == (0, 0.5)
            assert shading_max == 0.5
        else:
            assert axes.get_xlim() == (0, 1)
            assert axes.spines["right"].get_position() == ("outward", 0)
            assert axes.spines["top"].get_bounds() is None
            assert shading_max > 0.5

        ordinary_points = axes.collections[-2]
        np.testing.assert_allclose(ordinary_points.get_offsets(), [[largest_share, 0.6]])
        np.testing.assert_allclose(metro_handles[0].get_offsets(), [[0.3, 0.7]])
        np.testing.assert_allclose(metro_handles[0].get_facecolors(), [to_rgba(APPLE_GREEN)])
        assert axes.get_xlim()[1] > largest_share
        pd.testing.assert_frame_equal(scores_df, original_df)
    finally:
        plt.close(figure)


def test_comparison_preparation_uses_saved_regular_capy(tmp_path, monkeypatch):
    from national_figures import prepare_grid_vs_national_scores as preparation
    from national_pipeline.pipeline_config import PipelineConfig

    metrics_df = pd.DataFrame(
        {
            "study_area_id": ["metro", "metro"],
            "census_year": [2020, 2020],
            "geography_level": ["tracts", "tracts"],
            "population_comparison": ["white_black", "white_black"],
            "metric": [MetricName.CAPY, MetricName.CAPY_EXACT],
            "value": [0.5, 0.4],
        }
    )
    definitions_df = pd.DataFrame(
        {"study_area_id": ["metro"], "name": ["New York"], "metro_code": [MetroCode.NEW_YORK]}
    )
    summary_df = pd.DataFrame(
        {
            "study_area_id": ["metro"],
            "census_year": [2020],
            "geography_level": ["tracts"],
            "retained_WHITE": [20],
            "retained_BLACK": [20],
            "retained_POC": [30],
        }
    )
    monkeypatch.setattr(
        preparation,
        "read_national_figure_inputs",
        lambda *_: (metrics_df, definitions_df, summary_df),
    )
    config = PipelineConfig(
        study_area_type="cbsa",
        population_comparisons=(PopulationComparison.WHITE_BLACK,),
        metric_names=(MetricName.CAPY, MetricName.CAPY_EXACT),
    )
    preparation.prepare_grid_vs_national_scores(config, tmp_path, tmp_path)
    saved_df = pd.read_parquet(tmp_path / "tract_scores.parquet")

    assert saved_df[MetricName.CAPY].tolist() == [0.5]
    assert MetricName.CAPY_EXACT not in saved_df

    metrics_df.loc[0, "study_area_id"] = None
    with pytest.raises(ValueError, match="Pipeline score rows are missing"):
        preparation.prepare_grid_vs_national_scores(config, tmp_path, tmp_path)
    pd.testing.assert_frame_equal(pd.read_parquet(tmp_path / "tract_scores.parquet"), saved_df)
