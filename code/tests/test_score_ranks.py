"""Population selection and ascending average rank conventions."""

import numpy as np
import pandas as pd
import pytest
from national_figures.prepare_national_results import PRIMARY_METRICS
from national_pipeline.compute_metrics.metric_types import MetricName, PopulationComparison
from national_pipeline.geography_types import GeographyLevel

HISTORY_YEARS = [1980, 1990, 2000, 2010, 2020]
from national_figures.prepare_score_ranks import select_population_rank_sample


def test_ranks_use_largest_complete_hundred_and_ascending_average_ties():
    scores = []
    outcomes = []

    for area_number in range(103):
        identity = {
            "study_area_id": f"area_{area_number:03d}",
            "census_year": 2020,
            "geography_level": "tracts",
        }
        outcomes.append({**identity, "retained_TOTPOP": 1_000_000 - area_number})

        for metric in PRIMARY_METRICS:
            value = float(area_number // 2)

            if area_number == 0 and metric == "dissimilarity":
                value = np.nan

            scores.append({**identity, "metric": metric, "value": value})

    ranks_df = select_population_rank_sample(pd.DataFrame(scores), pd.DataFrame(outcomes))
    assert len(ranks_df) == 100
    assert ranks_df.index[0] == "area_001"
    assert ranks_df.index[-1] == "area_100"
    assert ranks_df.loc["area_001", "capy_rank"] == 1
    assert ranks_df.loc["area_002", "capy_rank"] == 2.5
    assert ranks_df.loc["area_003", "capy_rank"] == 2.5


@pytest.mark.parametrize("selected_count", [1, 2, 3])
def test_rank_preparation_and_plotting_use_only_selected_primary_metrics(
    selected_count, tmp_path, monkeypatch
):
    from national_figures import plot_score_ranks as plotting
    from national_figures import prepare_score_ranks as preparation
    from national_pipeline.pipeline_config import PipelineConfig

    metrics = (MetricName.CAPY, MetricName.DISSIMILARITY, MetricName.MORAN_ROW_STANDARDIZED)
    config = PipelineConfig(
        metric_names=metrics[:selected_count],
        census_geography_years=(2020,),
        census_geography_levels=(GeographyLevel.TRACT,),
        population_comparisons=(PopulationComparison.WHITE_BLACK,),
    )
    scores_df = pd.DataFrame(
        [
            {
                "study_area_id": area,
                "census_year": 2020,
                "geography_level": "tracts",
                "population_comparison": "white_black",
                "metric": metric,
                "value": np.nan
                if area == "c" and metric == MetricName.MORAN_ROW_STANDARDIZED
                else value,
            }
            for area, value in (("a", 0.4), ("b", 0.6), ("c", 0.7))
            for metric in metrics
        ]
    )
    definitions_df = pd.DataFrame(
        {"study_area_id": ["a", "b", "c"], "definition_population": [200000, 300000, 400000]}
    )
    summary_df = pd.DataFrame(
        {
            "study_area_id": ["a", "b", "c"],
            "census_year": [2020, 2020, 2020],
            "geography_level": ["tracts", "tracts", "tracts"],
            "retained_TOTPOP": [200000, 300000, 400000],
        }
    )
    monkeypatch.setattr(
        preparation,
        "read_national_figure_inputs",
        lambda *_: (scores_df, definitions_df, summary_df),
    )
    if selected_count == 1:
        with pytest.raises(ValueError, match="at least two"):
            preparation.prepare_score_rank_data(config, tmp_path, tmp_path, tmp_path / "tables")
        assert not (tmp_path / "rank_rows.parquet").exists()
        return

    preparation.prepare_score_rank_data(config, tmp_path, tmp_path, tmp_path / "tables")
    ranks_df = pd.read_parquet(tmp_path / "rank_rows.parquet")
    assert {column for column in ranks_df if column.endswith("_rank")} == {
        f"{metric}_rank" for metric in metrics[:selected_count]
    }
    assert set(ranks_df.study_area_id) == ({"a", "b", "c"} if selected_count == 2 else {"a", "b"})
    correlations_df = pd.read_parquet(tmp_path / "tables/rank_correlations.parquet")
    assert len(correlations_df) == (1 if selected_count == 2 else 3)
    plotting.plot_score_rank_comparisons(config, tmp_path / "figures", tmp_path)
    assert len(list((tmp_path / "figures").rglob("*.png"))) == len(correlations_df)


def test_rank_preparation_rejects_missing_selected_score_before_writing(tmp_path, monkeypatch):
    from national_figures import prepare_score_ranks as preparation
    from national_pipeline.pipeline_config import PipelineConfig

    scores_df = pd.DataFrame(
        [
            {
                "study_area_id": area,
                "census_year": 2020,
                "geography_level": "tracts",
                "population_comparison": "white_black",
                "metric": metric,
                "value": 0.6,
            }
            for area, metric in (("a", "capy"), ("a", "dissimilarity"), ("b", "capy"))
        ]
    )
    definitions_df = pd.DataFrame(
        {"study_area_id": ["a", "b"], "definition_population": [200000, 300000]}
    )
    summary_df = pd.DataFrame(
        {
            "study_area_id": ["a", "b"],
            "census_year": [2020, 2020],
            "geography_level": ["tracts", "tracts"],
            "retained_TOTPOP": [200000, 300000],
        }
    )
    monkeypatch.setattr(
        preparation,
        "read_national_figure_inputs",
        lambda *_: (scores_df, definitions_df, summary_df),
    )
    with pytest.raises(ValueError, match="score rows are missing"):
        preparation.prepare_score_rank_data(
            PipelineConfig(
                metric_names=(MetricName.CAPY, MetricName.DISSIMILARITY),
                census_geography_years=(2020,),
                census_geography_levels=(GeographyLevel.TRACT,),
                population_comparisons=(PopulationComparison.WHITE_BLACK,),
            ),
            tmp_path,
            tmp_path / "results",
            tmp_path / "tables",
        )
    assert not (tmp_path / "results").exists()
