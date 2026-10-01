"""National rendering reads prepared cohorts and never rewrites numerical inputs."""

import sys
from pathlib import Path

import make_figures
import pandas as pd
import pytest
import run_experiment
from national_figures import prepare_national_results
from national_pipeline.compute_metrics.metric_types import PopulationComparison
from national_pipeline.geography_types import GeographyLevel


def test_national_commands_prepare_once_then_plot_without_pipeline_access(tmp_path, monkeypatch):
    area_ids = ["cbsa_10000", "cbsa_10001"]
    definitions_df = pd.DataFrame(
        {
            "study_area_id": area_ids,
            "name": ["First", "Second"],
            "definition_population": [300000, 200000],
        }
    )
    scores = []
    outcomes = []

    for level in (GeographyLevel.TRACT, GeographyLevel.BLOCK_GROUP, GeographyLevel.BLOCK):
        years = (
            [1980, 1990, 2000, 2010, 2020]
            if level == GeographyLevel.TRACT
            else [1990, 2000, 2010, 2020]
        )

        for year in years:
            for number, area_id in enumerate(area_ids):
                identity = {"study_area_id": area_id, "census_year": year, "geography_level": level}
                outcomes.append(
                    {
                        **identity,
                        "retained_TOTPOP": 200000,
                        "retained_WHITE": 120000,
                        "retained_BLACK": 30000 + 10000 * number,
                    }
                )

                for comparison in PopulationComparison:
                    for metric in prepare_national_results.PRIMARY_METRICS:
                        scores.append(
                            {
                                **identity,
                                "population_comparison": comparison,
                                "metric": metric,
                                "value": 0.6 + number / 10,
                            }
                        )

    monkeypatch.setattr(
        prepare_national_results,
        "read_national_figure_inputs",
        lambda *_: (pd.DataFrame(scores), definitions_df, pd.DataFrame(outcomes)),
    )
    monkeypatch.setattr(
        sys, "argv", ["run_experiment.py", "national", "--data-directory", str(tmp_path)]
    )
    run_experiment.main()
    data_directory = tmp_path / "national/processed_data/history/CBSA20"
    saved_bytes = {path: path.read_bytes() for path in data_directory.iterdir()}
    original_read = pd.read_parquet

    def read_prepared_table(path, *args, **kwargs):
        assert Path(path).parent == data_directory
        return original_read(path, *args, **kwargs)

    def reject_preparation(*args, **kwargs):
        pytest.fail("Plotting must consume saved inputs without preparing or rewriting them")

    monkeypatch.setattr(prepare_national_results, "read_national_figure_inputs", reject_preparation)
    monkeypatch.setattr(pd, "read_parquet", read_prepared_table)
    monkeypatch.setattr(pd.DataFrame, "to_parquet", reject_preparation)
    monkeypatch.setattr(pd.DataFrame, "to_csv", reject_preparation)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "make_figures.py",
            "national",
            "--data-directory",
            str(tmp_path),
            "--output-directory",
            str(tmp_path / "images"),
        ],
    )
    make_figures.main()

    assert list((tmp_path / "images").rglob("*.png"))
    assert {path: path.read_bytes() for path in data_directory.iterdir()} == saved_bytes


def test_missing_prepared_histories_do_not_trigger_preparation(tmp_path, monkeypatch):
    def reject_preparation(*args, **kwargs):
        pytest.fail("Missing figure inputs require an explicit preparation run")

    monkeypatch.setattr(prepare_national_results, "read_national_figure_inputs", reject_preparation)
    monkeypatch.setattr(
        sys, "argv", ["make_figures.py", "national", "--data-directory", str(tmp_path)]
    )

    with pytest.raises(FileNotFoundError, match="trajectory_rows"):
        make_figures.main()
