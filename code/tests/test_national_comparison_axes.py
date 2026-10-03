"""National comparison drawers preserve caller ownership and supplied scientific values."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from national_figures.plot_score_ranks import plot_score_rank_pair
from national_pipeline.compute_metrics.metric_types import MetricName
from national_pipeline.pipeline_config import PipelineConfig


def test_score_rank_drawer_uses_prepared_ranks_on_the_supplied_axes():
    ranks_df = pd.DataFrame(
        {
            "capy_rank": [1.0, 3.0],
            "dissimilarity_rank": [3.0, 1.0],
        }
    )
    original_df = ranks_df.copy(deep=True)
    figure, score_axes = plt.subplots()
    figures_before = plt.get_fignums()
    plot_score_rank_pair(score_axes, ranks_df, MetricName.CAPY, MetricName.DISSIMILARITY)
    np.testing.assert_array_equal(score_axes.collections[0].get_offsets(), [[1, 3], [3, 1]])
    assert plt.get_fignums() == figures_before
    score_axes.set_yticks([1, 2, 3])
    assert list(score_axes.get_yticks()) == [1, 2, 3]
    pd.testing.assert_frame_equal(ranks_df, original_df)
    plt.close(figure)


def test_composition_uses_saved_fit_endpoints_and_matching_legend_lines(tmp_path, monkeypatch):
    from national_figures import plot_population_composition as plotting

    scores_df = pd.DataFrame(
        {
            "metric": ["capy", "capy"],
            "census_year": [2000, 2000],
            "rho": [0.1, 0.4],
            "value": [0.5, 0.6],
        }
    )
    fits_df = pd.DataFrame(
        {
            "metric": ["capy", "capy"],
            "census_year": [2000, 2000],
            "rho": [0.1, 0.4],
            "value": [0.2, 0.9],
        }
    )
    scores_df.to_parquet(tmp_path / "composition_rows.parquet", index=False)
    fits_df.to_parquet(tmp_path / "composition_fits.parquet", index=False)
    figures = []
    legends = []
    monkeypatch.setattr(plotting, "save_plot", lambda figure, path: figures.append(figure))
    monkeypatch.setattr(plotting, "save_legend", lambda handles, path: legends.append(handles))
    plotting.plot_population_composition(PipelineConfig(), tmp_path / "figures", tmp_path)
    assert len(figures) == len(legends) == 1
    axes = figures[0].axes[0]
    fitted_line = legends[0][0]
    np.testing.assert_allclose(
        np.interp(fits_df.rho, fitted_line.get_xdata(), fitted_line.get_ydata()), [0.2, 0.9]
    )
    assert legends[0][-1].get_label() == "Observed minimum"
    assert all(line in axes.lines for line in legends[0])
    plt.close(figures[0])
