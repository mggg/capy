"""Historical coverage uses original county populations and a fixed pre-filter tract cohort."""

import pandas as pd
import pytest
from national_figures.measure_historical_coverage import (
    measure_1980_cbsa_coverage,
    read_1980_cbsa_coverage,
)
from national_figures.prepare_national_results import select_score_histories
from national_pipeline.compute_metrics.metric_types import MetricName, PopulationComparison
from national_pipeline.geography_types import GeographyLevel, StudyAreaType
from national_pipeline.pipeline_config import PipelineConfig


def test_coverage_threshold_missing_inputs_and_zero_population_are_explicit():
    definitions_df = pd.DataFrame(
        {
            "study_area_id": ["below", "exact", "above", "missing_county", "missing_tract", "zero"],
            "county_codes": [
                ["01001"],
                ["01001", "01003"],
                ["01001"],
                ["01005"],
                ["01001"],
                ["01007"],
            ],
            "definition_population": [999999] * 6,
        }
    )
    tract_population_df = pd.DataFrame(
        {
            "study_area_id": ["below", "exact", "above", "missing_county", "zero"],
            "TOTPOP": [89, 180, 101, 100, 0],
        }
    )
    county_population_df = pd.DataFrame(
        {"county_code": ["01001", "01003", "01007"], "TOTPOP": [100, 100, 0]}
    )
    original_df = definitions_df.copy(deep=True)
    coverage_df = measure_1980_cbsa_coverage(
        definitions_df, tract_population_df, county_population_df
    ).set_index("study_area_id")

    assert set(coverage_df.index[coverage_df.eligible]) == {"exact", "above"}
    assert coverage_df.loc["exact", "member_county_population"] == 200
    assert coverage_df.loc["exact", "coverage_fraction"] == 0.9
    assert coverage_df.loc["above", "coverage_fraction"] == 1.01
    assert coverage_df.loc["missing_county", "missing_county_codes"] == "01005"
    assert pd.isna(coverage_df.loc["missing_county", "member_county_population"])
    assert coverage_df.loc["missing_tract", "status"] == "missing_tract_population"
    assert coverage_df.loc["zero", "status"] == "zero_county_population"
    pd.testing.assert_frame_equal(definitions_df, original_df)


@pytest.mark.parametrize("comparison", list(PopulationComparison))
def test_coverage_excludes_complete_histories_for_both_comparisons_only_when_1980_tracts_are_used(
    comparison,
):
    config = PipelineConfig(study_area_type=StudyAreaType.CBSA)
    scores_df = pd.DataFrame(
        [
            {
                "study_area_id": area,
                "census_year": year,
                "geography_level": level,
                "population_comparison": comparison,
                "metric": MetricName.CAPY,
                "value": 0.5,
            }
            for area in ("eligible", "excluded")
            for year in (1980, 1990, 2020)
            for level in (GeographyLevel.TRACT, GeographyLevel.BLOCK)
        ]
    )
    selection = {(comparison, GeographyLevel.TRACT): [1980, 1990, 2020]}
    with pytest.raises(ValueError, match="coverage eligibility"):
        select_score_histories(scores_df, selection, (MetricName.CAPY,), config)

    result = select_score_histories(
        scores_df, selection, (MetricName.CAPY,), config, eligible_1980_cbsa_ids={"eligible"}
    )
    assert set(result.study_area_id) == {"eligible"}
    assert set(result.census_year) == {1980, 1990, 2020}

    for level in (GeographyLevel.TRACT, GeographyLevel.BLOCK):
        selection = {(comparison, level): [1990, 2020]}
        result = select_score_histories(
            scores_df, selection, (MetricName.CAPY,), config, eligible_1980_cbsa_ids=set()
        )
        assert set(result.study_area_id) == {"eligible", "excluded"}


def test_coverage_reader_uses_configured_county_totals_and_prefilter_assignments(tmp_path):
    config = PipelineConfig(
        study_area_type=StudyAreaType.CBSA,
        processed_population_directory="custom_population",
        study_area_directory="custom_areas",
    )
    population_directory = tmp_path / "custom_population/1980/counties"
    population_directory.mkdir(parents=True)
    pd.DataFrame(
        {"STATEA": ["01", "01"], "COUNTYA": ["001", "003"], "TOTPOP": [100, 100]}
    ).to_parquet(population_directory / "AL_1980_populations.parquet")
    study_directory = tmp_path / "custom_areas/cbsa/2020"
    study_directory.mkdir(parents=True)
    pd.DataFrame(
        {
            "study_area_id": ["metro", "metro"],
            "census_year": [1980, 2020],
            "geography_level": ["tracts", "tracts"],
            "TOTPOP": [180, 1000],
        }
    ).to_parquet(study_directory / "summary.parquet")
    definitions_df = pd.DataFrame(
        {
            "study_area_id": ["metro"],
            "county_codes": [["01001", "01003"]],
            "definition_population": [1000],
        }
    )
    coverage_df = read_1980_cbsa_coverage(config, tmp_path, definitions_df)
    assert coverage_df.iloc[0].coverage_fraction == 0.9
    assert coverage_df.iloc[0].eligible

    (population_directory / "AL_1980_populations.parquet").unlink()
    with pytest.raises(FileNotFoundError):
        read_1980_cbsa_coverage(config, tmp_path, definitions_df)


def test_preparation_saves_restricted_histories_and_inspectable_sensitivity(tmp_path, monkeypatch):
    from national_figures import prepare_national_results

    config = PipelineConfig(
        study_area_type=StudyAreaType.CBSA,
        census_geography_years=(1980, 2020),
        census_geography_levels=(GeographyLevel.TRACT,),
        metric_names=(MetricName.CAPY,),
    )
    population_directory = tmp_path / config.processed_population_directory / "1980/counties"
    population_directory.mkdir(parents=True)
    pd.DataFrame(
        {"STATEA": ["01", "01"], "COUNTYA": ["001", "003"], "TOTPOP": [100, 100]}
    ).to_parquet(population_directory / "AL_1980_populations.parquet")
    study_directory = tmp_path / config.study_area_directory / "cbsa/2020"
    study_directory.mkdir(parents=True)
    pd.DataFrame(
        {
            "study_area_id": ["kept", "omitted"],
            "census_year": [1980, 1980],
            "geography_level": ["tracts", "tracts"],
            "TOTPOP": [90, 89],
        }
    ).to_parquet(study_directory / "summary.parquet")
    definitions_df = pd.DataFrame(
        {
            "study_area_id": ["kept", "omitted"],
            "county_codes": [["01001"], ["01003"]],
            "definition_population": [200000, 200000],
        }
    )
    scores_df = pd.DataFrame(
        [
            {
                "study_area_id": area_id,
                "census_year": year,
                "geography_level": "tracts",
                "population_comparison": comparison,
                "metric": "capy",
                "value": value,
            }
            for area_id, value in (("kept", 0.6), ("omitted", 0.2))
            for year in (1980, 2020)
            for comparison in PopulationComparison
        ]
    )
    graph_summary_df = scores_df[prepare_national_results.IDENTITY_COLUMNS].drop_duplicates()
    monkeypatch.setattr(
        prepare_national_results,
        "read_national_figure_inputs",
        lambda *_: (scores_df, definitions_df, graph_summary_df),
    )
    output_directory = tmp_path / "prepared"
    prepare_national_results.prepare_national_figure_data(config, tmp_path, output_directory)

    restricted_df = pd.read_parquet(output_directory / "trajectory_rows.parquet")
    unrestricted_df = pd.read_parquet(
        output_directory / "trajectory_rows_without_coverage_cutoff.parquet"
    )
    comparison_df = pd.read_csv(output_directory / "historical_coverage_comparison.csv")
    coverage_df = pd.read_csv(output_directory / "1980_cbsa_population_coverage.csv")
    assert set(restricted_df.study_area_id) == {"kept"}
    assert set(unrestricted_df.study_area_id) == {"kept", "omitted"}
    assert set(restricted_df.population_comparison) == set(PopulationComparison)
    assert set(restricted_df.census_year) == {1980, 2020}
    assert comparison_df.area_count_restricted.eq(1).all()
    assert comparison_df.area_count_unrestricted.eq(2).all()
    assert comparison_df.mean_score_change.tolist() == pytest.approx([0.2] * 4)
    assert set(coverage_df.status) == {"eligible", "below_threshold"}


def test_county_rename_uses_original_population_but_county_creation_remains_missing():
    definitions_df = pd.DataFrame(
        {
            "study_area_id": ["miami", "denver"],
            "county_codes": [["12086"], ["08001", "08014"]],
        }
    )
    tracts_df = pd.DataFrame({"study_area_id": ["miami", "denver"], "TOTPOP": [90, 90]})
    counties_df = pd.DataFrame({"county_code": ["12025", "08001"], "TOTPOP": [100, 100]})
    coverage_df = measure_1980_cbsa_coverage(definitions_df, tracts_df, counties_df).set_index(
        "study_area_id"
    )

    assert coverage_df.loc["miami", "eligible"]
    assert coverage_df.loc["miami", "population_county_codes"] == "12025"
    assert coverage_df.loc["miami", "member_county_population"] == 100
    assert not coverage_df.loc["denver", "eligible"]
    assert coverage_df.loc["denver", "missing_county_codes"] == "08014"
    assert pd.isna(coverage_df.loc["denver", "member_county_population"])
