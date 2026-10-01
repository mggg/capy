"""Ranked table population units and denominators."""

import pandas as pd
from national_figures.prepare_national_results import PRIMARY_METRICS
from national_pipeline.compute_metrics.metric_types import MetricName, PopulationComparison
from national_pipeline.geography_types import GeographyLevel

HISTORY_YEARS = [1980, 1990, 2000, 2010, 2020]


def test_publication_table_black_share_uses_total_population():
    from national_figures.prepare_ranked_table import build_ranked_population_table

    scores_df = pd.DataFrame(
        [
            {
                "study_area_id": "metro",
                "census_year": year,
                "geography_level": "tracts",
                "population_comparison": "white_black",
                "metric": metric,
                "value": 0.6,
            }
            for year in (2020,)
            for metric in PRIMARY_METRICS
        ]
    )
    definitions_df = pd.DataFrame({"study_area_id": ["metro"], "name": ["Example metro"]})
    outcomes_df = pd.DataFrame(
        {
            "study_area_id": ["metro"],
            "census_year": [2020],
            "geography_level": ["tracts"],
            "retained_TOTPOP": [1_000_000],
            "retained_WHITE": [600_000],
            "retained_BLACK": [200_000],
        }
    )
    table_df = build_ranked_population_table(scores_df, definitions_df, outcomes_df)
    assert table_df.loc[0, "population_millions"] == 1
    assert table_df.loc[0, "second_group_share_total_population"] == 0.2
    assert set(PRIMARY_METRICS).issubset(table_df.columns)


def test_ranked_table_excludes_nonfinite_current_scores_and_rejects_missing_accounting():
    import numpy as np
    import pytest
    from national_figures.prepare_ranked_table import build_ranked_population_table

    scores_df = pd.DataFrame(
        [
            {
                "study_area_id": area_id,
                "census_year": 2020,
                "geography_level": "tracts",
                "population_comparison": "white_black",
                "metric": "capy",
                "value": value,
            }
            for area_id, value in (
                ("valid", 0.6),
                ("positive_inf", np.inf),
                ("negative_inf", -np.inf),
            )
        ]
    )
    definitions_df = pd.DataFrame({"study_area_id": ["valid"], "name": ["Valid"]})
    summary_df = pd.DataFrame(
        {
            "study_area_id": ["valid"],
            "census_year": [2020],
            "geography_level": ["tracts"],
            "retained_TOTPOP": [100],
            "retained_WHITE": [60],
            "retained_BLACK": [20],
        }
    )
    table_df = build_ranked_population_table(scores_df, definitions_df, summary_df)
    assert table_df.study_area_id.tolist() == ["valid"]
    assert table_df["rank"].tolist() == [1]
    assert "capy_1980" not in table_df

    with pytest.raises(ValueError, match="study-area name"):
        build_ranked_population_table(scores_df, definitions_df.iloc[:0], summary_df)
    with pytest.raises(ValueError, match="population accounting"):
        build_ranked_population_table(scores_df, definitions_df, summary_df.iloc[:0])


def test_ranked_table_accepts_capy_only_and_ignores_unselected_saved_scores(tmp_path, monkeypatch):
    from national_figures import prepare_ranked_table as preparation
    from national_pipeline.pipeline_config import PipelineConfig

    config = PipelineConfig(
        metric_names=(MetricName.CAPY,),
        census_geography_years=(2020,),
        census_geography_levels=(GeographyLevel.TRACT,),
        population_comparisons=(PopulationComparison.WHITE_BLACK,),
    )
    scores_df = pd.DataFrame(
        [
            {
                "study_area_id": "metro",
                "census_year": 2020,
                "geography_level": "tracts",
                "population_comparison": "white_black",
                "metric": metric,
                "value": 0.6,
            }
            for metric in PRIMARY_METRICS
        ]
    )
    definitions_df = pd.DataFrame(
        {"study_area_id": ["metro"], "name": ["Example"], "definition_population": [200000]}
    )
    summary_df = pd.DataFrame(
        {
            "study_area_id": ["metro"],
            "census_year": [2020],
            "geography_level": ["tracts"],
            "retained_TOTPOP": [200000],
            "retained_WHITE": [120000],
            "retained_BLACK": [40000],
        }
    )
    monkeypatch.setattr(
        preparation,
        "read_national_figure_inputs",
        lambda *_: (scores_df, definitions_df, summary_df),
    )
    preparation.prepare_ranked_population_table(config, tmp_path, tmp_path)
    table_df = pd.read_parquet(tmp_path / "top_100_capy.parquet")
    assert table_df.capy.tolist() == [0.6]
    assert "dissimilarity" not in table_df
    assert "moran_row_standardized" not in table_df
    assert "capy_1980" not in table_df


def test_ranked_table_rejects_missing_selected_supplementary_score(tmp_path, monkeypatch):
    import pytest
    from national_figures import prepare_ranked_table as preparation
    from national_pipeline.pipeline_config import PipelineConfig

    scores_df = pd.DataFrame(
        {
            "study_area_id": ["metro"],
            "census_year": [2020],
            "geography_level": ["tracts"],
            "population_comparison": ["white_black"],
            "metric": ["capy"],
            "value": [0.6],
        }
    )
    definitions_df = pd.DataFrame(
        {"study_area_id": ["metro"], "name": ["Example"], "definition_population": [200000]}
    )
    summary_df = pd.DataFrame(
        {
            "study_area_id": ["metro"],
            "census_year": [2020],
            "geography_level": ["tracts"],
            "retained_TOTPOP": [200000],
            "retained_WHITE": [120000],
            "retained_BLACK": [40000],
        }
    )
    monkeypatch.setattr(
        preparation,
        "read_national_figure_inputs",
        lambda *_: (scores_df, definitions_df, summary_df),
    )
    with pytest.raises(ValueError, match="score rows are missing"):
        preparation.prepare_ranked_population_table(
            PipelineConfig(
                census_geography_years=(2020,),
                census_geography_levels=(GeographyLevel.TRACT,),
                metric_names=(MetricName.CAPY, MetricName.DISSIMILARITY),
                population_comparisons=(PopulationComparison.WHITE_BLACK,),
            ),
            tmp_path,
            tmp_path / "results",
        )
    assert not (tmp_path / "results").exists()


def test_ranked_tables_and_rank_plots_keep_configured_selections_separate(tmp_path, monkeypatch):
    from national_figures import prepare_ranked_table as table_preparation
    from national_figures import prepare_score_ranks as rank_preparation
    from national_figures.plot_score_ranks import plot_score_rank_comparisons
    from national_pipeline.pipeline_config import PipelineConfig

    config = PipelineConfig(
        census_geography_years=(2000, 2010),
        census_geography_levels=(GeographyLevel.COUNTY, GeographyLevel.BLOCK_GROUP),
        population_comparisons=(PopulationComparison.WHITE_BLACK, PopulationComparison.WHITE_POC),
        metric_names=(MetricName.CAPY, MetricName.DISSIMILARITY),
    )
    identities = [
        {"census_year": year, "geography_level": level, "study_area_id": area}
        for year in config.census_geography_years
        for level in config.census_geography_levels
        for area in ("a", "b")
    ]
    scores_df = pd.DataFrame(
        [
            {
                **identity,
                "population_comparison": comparison,
                "metric": metric,
                "value": 0.8
                if (identity["study_area_id"] == "a") == (identity["census_year"] == 2000)
                else 0.4,
            }
            for identity in identities
            for comparison in config.population_comparisons
            for metric in config.metric_names
        ]
    )
    summary_df = pd.DataFrame(
        [
            {**identity, "retained_TOTPOP": 200000, "retained_BLACK": 40000, "retained_POC": 80000}
            for identity in identities
        ]
    )
    definitions_df = pd.DataFrame(
        {"study_area_id": ["a", "b"], "name": ["A", "B"], "definition_population": [200000, 300000]}
    )
    for preparation in (table_preparation, rank_preparation):
        monkeypatch.setattr(
            preparation,
            "read_national_figure_inputs",
            lambda *_: (scores_df, definitions_df, summary_df),
        )
    table_preparation.prepare_ranked_population_table(config, tmp_path, tmp_path)
    rank_preparation.prepare_score_rank_data(config, tmp_path, tmp_path, tmp_path / "tables")
    table_df = pd.read_parquet(tmp_path / "top_100_capy.parquet")
    ranks_df = pd.read_parquet(tmp_path / "rank_rows.parquet")
    selection_columns = ["census_year", "geography_level", "population_comparison"]
    assert len(table_df.groupby(selection_columns)) == 8
    assert len(ranks_df.groupby(selection_columns)) == 8
    for (year, _, comparison), selection_df in table_df.groupby(selection_columns):
        assert selection_df.sort_values("rank").study_area_id.tolist() == (
            ["a", "b"] if year == 2000 else ["b", "a"]
        )
        assert selection_df.second_group_share_total_population.tolist() == (
            [0.2, 0.2] if comparison == "white_black" else [0.4, 0.4]
        )
    for _, selection_df in ranks_df.groupby(selection_columns):
        assert sorted(selection_df.capy_rank) == [1.0, 2.0]
    plot_score_rank_comparisons(config, tmp_path / "figures", tmp_path)
    assert len(list((tmp_path / "figures").rglob("*.png"))) == 8
