"""Population shares, selections, and preparation failure ownership."""

import pandas as pd
import pytest


def test_national_score_shares_use_retained_comparison_populations():
    from national_figures.prepare_grid_vs_national_scores import (
        COMPARISON_METRICS,
        attach_tract_score_populations,
    )

    metrics_df = pd.DataFrame(
        [
            {
                "study_area_id": "cbsa_10180",
                "census_year": 2020,
                "geography_level": "tracts",
                "population_comparison": comparison,
                "metric": metric,
                "value": 0.6,
            }
            for comparison in ("white_black", "white_poc")
            for metric in COMPARISON_METRICS
        ]
    )
    definitions_df = pd.DataFrame(
        {"study_area_id": ["cbsa_10180"], "name": ["Example"], "metro_code": ["10180"]}
    )
    outcomes_df = pd.DataFrame(
        {
            "study_area_id": ["cbsa_10180"],
            "census_year": [2020],
            "geography_level": ["tracts"],
            "retained_WHITE": [600],
            "retained_BLACK": [200],
            "retained_POC": [400],
        }
    )
    scores_df = attach_tract_score_populations(metrics_df, definitions_df, outcomes_df)
    shares = scores_df.set_index("population_comparison").group_share
    assert shares["white_black"] == pytest.approx(0.25)
    assert shares["white_poc"] == pytest.approx(0.4)

    white_black_df = attach_tract_score_populations(
        metrics_df.loc[metrics_df.population_comparison.eq("white_black")],
        definitions_df,
        outcomes_df,
    )
    assert white_black_df.population_comparison.tolist() == ["white_black"]


@pytest.mark.parametrize("metric_names", [None, ("entropy_index",), ("moran_row_standardized",)])
def test_tract_score_reader_requests_only_selected_year_comparison_and_tracts(
    monkeypatch, tmp_path, metric_names
):
    from national_figures import prepare_grid_vs_national_scores as preparation
    from national_pipeline.compute_metrics.metric_types import MetricName, PopulationComparison
    from national_pipeline.geography_types import GeographyLevel, StudyAreaType
    from national_pipeline.pipeline_config import PipelineConfig

    config = PipelineConfig(
        study_area_type=StudyAreaType.CBSA,
        census_geography_years=(2020,),
        population_comparisons=(PopulationComparison.WHITE_BLACK,),
        metric_names=tuple(MetricName(name) for name in metric_names)
        if metric_names
        else preparation.COMPARISON_METRICS,
    )
    definitions_df = pd.DataFrame(
        {
            "study_area_id": ["metro"],
            "name": ["Example"],
            "metro_code": ["35620"],
            "definition_population": [200000],
        }
    )
    summary_df = pd.DataFrame(
        {
            "study_area_id": ["metro"],
            "census_year": [2020],
            "geography_level": ["tracts"],
            "retained_WHITE": [600],
            "retained_BLACK": [200],
            "retained_POC": [400],
        }
    )
    metrics_df = pd.DataFrame(
        [
            {
                "study_area_id": "metro",
                "census_year": 2020,
                "geography_level": "tracts",
                "population_comparison": "white_black",
                "metric": metric,
                "value": 0.6,
            }
            for metric in preparation.COMPARISON_METRICS
        ]
    )
    calls = []

    def read_inputs(config, root, selections):
        calls.append(selections)
        return metrics_df, definitions_df, summary_df

    monkeypatch.setattr(preparation, "read_national_figure_inputs", read_inputs)
    scores_df, top_10_df = preparation.read_tract_score_inputs(
        config, tmp_path, [2020], (PopulationComparison.WHITE_BLACK,)
    )
    assert calls == [{(PopulationComparison.WHITE_BLACK, GeographyLevel.TRACT): [2020]}]
    assert scores_df.population_comparison.tolist() == ["white_black"]
    assert top_10_df.study_area_id.tolist() == ["metro"]

    selected_metrics = set(config.metric_names)
    assert set(scores_df.columns).intersection(preparation.COMPARISON_METRICS) == selected_metrics

    from national_figures import plot_grid_vs_national_scores as plotting

    preparation.prepare_grid_vs_national_scores(config, tmp_path, tmp_path / "snapshot")
    plotting.plot_grid_vs_national_scores(config, tmp_path / "images", tmp_path / "snapshot")
    assert len(list((tmp_path / "images").rglob("TRACT_*_by_share.png"))) == 2 * len(
        selected_metrics
    )
    assert len(list((tmp_path / "images").rglob("*legend.png"))) == 2

    dropped_metric = next(iter(selected_metrics))
    metrics_df.drop(index=metrics_df.index[metrics_df.metric.eq(dropped_metric)], inplace=True)
    with pytest.raises(
        ValueError, match="Pipeline score rows are missing|No selected tract"
    ):
        preparation.read_tract_score_inputs(
            config, tmp_path, [2020], (PopulationComparison.WHITE_BLACK,)
        )


def test_empty_score_selection_does_not_publish_tables(tmp_path, monkeypatch):
    from national_figures import prepare_grid_vs_national_scores as preparation
    from national_pipeline.compute_metrics.metric_types import MetricName
    from national_pipeline.pipeline_config import PipelineConfig

    scores_df = pd.DataFrame(
        columns=[
            "study_area_id",
            "census_year",
            "geography_level",
            "population_comparison",
            "metric",
            "value",
        ]
    )
    summary_df = pd.DataFrame(columns=["study_area_id", "census_year", "geography_level"])
    monkeypatch.setattr(
        preparation,
        "read_national_figure_inputs",
        lambda *_: (scores_df, pd.DataFrame(), summary_df),
    )
    with pytest.raises(ValueError, match="No selected tract observations"):
        preparation.prepare_grid_vs_national_scores(
            PipelineConfig(metric_names=(MetricName.ENTROPY_INDEX,)), tmp_path, tmp_path / "results"
        )
    assert not (tmp_path / "results").exists()
