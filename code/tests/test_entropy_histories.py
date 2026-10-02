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
    from national_figures import plot_entropy_by_geography, prepare_entropy_by_geography

    preparation_calls = []
    plotting_calls = []
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
    for command in (run_experiment, make_figures):
        monkeypatch.setattr(
            sys,
            "argv",
            [command.__name__, "entropy-by-geography", "--data-directory", str(tmp_path)],
        )
        command.main()

    assert preparation_calls[0][2] == plotting_calls[0][2]
    assert (
        plotting_calls[0][2] == tmp_path / "national/processed_data/entropy_by_geography/WB_CBSA20"
    )
