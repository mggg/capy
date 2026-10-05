"""Entropy cohorts follow each resolution’s selected source coverage."""

import numpy as np
import pandas as pd

HISTORY_YEARS = [1980, 1990, 2000, 2010, 2020]


def test_entropy_histories_keep_a_fixed_cohort_over_each_levels_available_decades():
    from national_figures.prepare_entropy_by_geography import (
        ENTROPY_LEVELS,
        select_entropy_histories,
    )
    from national_pipeline.geography_types import GeographyLevel

    top_10_ids = [f"metro_{number}" for number in range(10)]
    area_ids = [*top_10_ids, "missing_1980", "missing_2000", "at_threshold"]
    definitions_df = pd.DataFrame(
        {
            "study_area_id": area_ids,
            "definition_population": [200000] * (len(area_ids) - 1) + [100000],
        }
    )
    rows = []

    for level in ENTROPY_LEVELS:
        years = HISTORY_YEARS if level == GeographyLevel.TRACT else HISTORY_YEARS[1:]

        for area_id in area_ids:
            for year in years:
                if area_id == "missing_1980" and year == 1980:
                    continue

                rows.append(
                    {
                        "study_area_id": area_id,
                        "census_year": year,
                        "geography_level": level,
                        "population_comparison": "white_black",
                        "metric": "entropy_index",
                        "value": np.nan if area_id == "missing_2000" and year == 2000 else 0.5,
                    }
                )

    histories_df = select_entropy_histories(
        pd.DataFrame(rows),
        definitions_df,
        {
            level: HISTORY_YEARS if level == GeographyLevel.TRACT else HISTORY_YEARS[1:]
            for level in ENTROPY_LEVELS
        },
    )

    for level, level_df in histories_df.groupby("geography_level"):
        expected_ids = set(top_10_ids)
        expected_years = HISTORY_YEARS

        if level != GeographyLevel.TRACT:
            expected_ids.add("missing_1980")
            expected_years = HISTORY_YEARS[1:]

        assert set(level_df.study_area_id) == expected_ids
        assert level_df.groupby("study_area_id").census_year.apply(list).tolist() == [
            expected_years
        ] * len(expected_ids)


def test_entropy_commands_share_compact_prepared_data_path(tmp_path, monkeypatch):
    import sys

    import make_figures
    import run_experiment
    from national_figures import (
        plot_entropy_by_geography,
        plot_national_results,
        prepare_entropy_by_geography,
        prepare_national_results,
    )

    preparation_calls = []
    plotting_calls = []
    national_calls = []
    configuration_paths = []
    load_configuration = run_experiment.load_configuration

    def load_and_record_configuration(path):
        configuration_paths.append(path)
        return load_configuration(path)

    monkeypatch.setattr(
        prepare_entropy_by_geography,
        "prepare_entropy_data",
        lambda *args: preparation_calls.append(args),
    )
    monkeypatch.setattr(
        plot_entropy_by_geography,
        "plot_entropy_by_geography",
        lambda *args: plotting_calls.append(args),
    )
    monkeypatch.setattr(
        prepare_national_results,
        "prepare_national_figure_data",
        lambda *args: national_calls.append(args),
    )
    monkeypatch.setattr(
        plot_national_results, "plot_national_figures", lambda *args: national_calls.append(args)
    )
    for command in (run_experiment, make_figures):
        configuration_paths.clear()
        monkeypatch.setattr(command, "load_configuration", load_and_record_configuration)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                command.__name__,
                "entropy-by-geography",
                "national",
                "entropy-by-geography",
                "--data-directory",
                str(tmp_path),
            ],
        )
        command.main()
        assert len(configuration_paths) == 1

    assert len(preparation_calls) == len(plotting_calls) == 2
    assert len(national_calls) == 2
    assert preparation_calls[0][2] == preparation_calls[1][2] == plotting_calls[0][2]
    assert (
        national_calls[0][2]
        == national_calls[1][2]
        == (tmp_path / "national/processed_data/history/CBSA20")
    )
    assert (
        plotting_calls[0][2] == tmp_path / "national/processed_data/entropy_by_geography/WB_CBSA20"
    )


def test_history_year_selection_preserves_image_order_and_omits_dependency_only_geography():
    from national_figures.prepare_national_results import select_history_years
    from national_pipeline.compute_metrics.metric_types import PopulationComparison
    from national_pipeline.geography_types import GeographyLevel
    from national_pipeline.pipeline_config import PipelineConfig

    config = PipelineConfig(
        census_geography_years=(1990, 1980),
        census_geography_levels=(GeographyLevel.BLOCK, GeographyLevel.COUNTY, GeographyLevel.TRACT),
        population_comparisons=(PopulationComparison.WHITE_POC, PopulationComparison.WHITE_BLACK),
    )

    assert list(select_history_years(config).items()) == [
        ((PopulationComparison.WHITE_BLACK, GeographyLevel.TRACT), [1980, 1990]),
        ((PopulationComparison.WHITE_BLACK, GeographyLevel.BLOCK), [1990]),
        ((PopulationComparison.WHITE_POC, GeographyLevel.TRACT), [1980, 1990]),
        ((PopulationComparison.WHITE_POC, GeographyLevel.BLOCK), [1990]),
    ]


def test_entropy_preparation_reads_only_selected_white_black_years_and_levels(
    tmp_path, monkeypatch
):
    from national_figures import prepare_entropy_by_geography as preparation
    from national_pipeline.geography_types import GeographyLevel
    from national_pipeline.pipeline_config import PipelineConfig

    config = PipelineConfig(
        census_geography_years=(1990, 1980),
        census_geography_levels=(GeographyLevel.COUNTY, GeographyLevel.BLOCK, GeographyLevel.TRACT),
    )
    expected_selections = {
        ("white_black", "tracts"): [1980, 1990],
        ("white_black", "blocks"): [1990],
    }
    metrics_df = pd.DataFrame(
        [
            {
                "study_area_id": "metro_1",
                "census_year": year,
                "geography_level": level,
                "population_comparison": comparison,
                "metric": "entropy_index",
                "value": 0.5,
            }
            for (comparison, level), years in expected_selections.items()
            for year in years
        ]
    )
    definitions_df = pd.DataFrame({"study_area_id": ["metro_1"], "definition_population": [200000]})

    def read_inputs(config, root, selections):
        assert list(selections.items()) == list(expected_selections.items())
        return metrics_df, definitions_df, pd.DataFrame()

    monkeypatch.setattr(preparation, "read_national_figure_inputs", read_inputs)
    preparation.prepare_entropy_data(config, tmp_path, tmp_path / "prepared")

    histories_df = pd.read_parquet(tmp_path / "prepared/entropy_histories.parquet")
    assert histories_df.census_year.tolist() == [1980, 1990, 1990]
    assert histories_df.geography_level.tolist() == ["tracts", "tracts", "blocks"]
