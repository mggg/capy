import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SCRIPTS = [
    "capy_core/download/download_geographies.py",
    "capy_core/download/download_population_tables.py",
    "capy_core/graphs.py",
    "capy_core/metrics.py",
    "capy_core/preprocessing/build_census_geographies.py",
    "capy_core/preprocessing/overlap_quality.py",
    "capy_core/preprocessing/overlaps.py",
    "capy_core/preprocessing/study_areas.py",
    "capy_core/process_results.py",
    "experiment_code/baseline/visualization/line_plots/generate_figures.py",
    "experiment_code/baseline/visualization/line_plots/plot_family_grids.py",
    "experiment_code/baseline/visualization/line_plots/plot_grid_all_census_areas.py",
    "experiment_code/baseline/visualization/line_plots/plot_grid_top10.py",
    "experiment_code/baseline/visualization/metrics_vs_rho/metrics_vs_rho.py",
    "experiment_code/baseline/visualization/rank_comparisons/rank_comparisons_single.py",
    "experiment_code/iowa_scripts/make_clustered_iowa_plots.py",
    "experiment_code/iowa_scripts/make_iowa_files.py",
    "experiment_code/iowa_scripts/make_iowa_legend.py",
    "experiment_code/iowa_scripts/make_isol_iowa_plots.py",
    "experiment_code/iowa_scripts/make_kclustered_iowa_plots.py",
    "experiment_code/iowa_scripts/make_uniform_iowa_plots.py",
]


@pytest.mark.parametrize("script", CLI_SCRIPTS)
def test_command_help_exits_without_running_workflow(script):
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / script), "--help"],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(REPO_ROOT),
            "CENSUS_API_KEY": "unused-help-test-key",
            "MPLBACKEND": "Agg",
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert "--help" in result.stdout


@pytest.mark.parametrize(
    "stage", ["download_geographies", "download_population_tables"]
)
@pytest.mark.parametrize(
    "year_args, expected_years",
    [
        (["--year", "1980", "-y", "1990", "--years", "2000,2010"], [1980, 1990]),
        (["--years", "2000,2010"], [2000, 2010]),
    ],
)
def test_download_cli_preserves_year_selection_and_path_options(
    stage, year_args, expected_years, tmp_path
):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            f"capy_core.download.{stage}",
            "--level",
            "places",
            *year_args,
            "--env-file",
            str(tmp_path / "missing.env"),
            "--output-dir",
            str(tmp_path / "output"),
            "--work-dir",
            str(tmp_path / "work"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    # Historical places are skipped before any downloads or output writes.
    assert result.stdout.splitlines() == [
        f"Skipping {year} places: only 2020 is used in the pipeline."
        for year in expected_years
    ]
    assert not (tmp_path / "output").exists()
