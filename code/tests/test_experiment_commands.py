"""Keep numerical execution and figure rendering independent at the command boundary."""

import sys
from pathlib import Path

import make_figures
import pytest
import run_experiment
from national_figures import compare_capy_weights, plot_capy_weights, plot_national_results


def test_plot_commands_run_in_order_without_computing(monkeypatch):
    calls = []
    monkeypatch.setattr(
        plot_capy_weights, "plot_capy_weight_comparison", lambda *args: calls.append("weights")
    )
    monkeypatch.setattr(
        plot_national_results, "plot_national_figures", lambda *args: calls.append("national")
    )
    monkeypatch.setattr(
        compare_capy_weights,
        "run_capy_weight_comparison",
        lambda *args: pytest.fail("Plotting must not compute experiment results"),
    )
    monkeypatch.setattr(sys, "argv", ["make_figures.py", "capy-weights", "national"])

    make_figures.main()

    assert calls == ["weights", "national"]


def test_experiment_command_runs_without_plotting(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        compare_capy_weights, "run_capy_weight_comparison", lambda *args: calls.append(args)
    )
    monkeypatch.setattr(
        plot_capy_weights,
        "plot_capy_weight_comparison",
        lambda *args: pytest.fail("Running experiments must not draw figures"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_experiment.py", "capy-weights", "capy-weights", "--data-directory", str(tmp_path)],
    )

    run_experiment.main()

    assert len(calls) == 2
    assert all(
        args[2] == tmp_path / "national/processed_data/capy_weights/CBSA20" for args in calls
    )
    assert (
        make_figures.FIGURE_DIRECTORIES["capy-weights"][0]
        == run_experiment.EXPERIMENT_DIRECTORIES["capy-weights"]
    )


def test_invalid_experiment_name_prevents_computation(monkeypatch):
    monkeypatch.setattr(
        compare_capy_weights,
        "run_capy_weight_comparison",
        lambda *args: pytest.fail("Invalid selection must fail before computing"),
    )
    monkeypatch.setattr(sys, "argv", ["run_experiment.py", "capy-weights", "unknown"])

    with pytest.raises(SystemExit) as error:
        run_experiment.main()

    assert error.value.code == 2


def test_experiment_failure_stops_later_workflows(monkeypatch):
    calls = []

    def fail_to_compute(*args):
        calls.append(args)
        raise ValueError("Invalid experiment inputs")

    monkeypatch.setattr(compare_capy_weights, "run_capy_weight_comparison", fail_to_compute)
    monkeypatch.setattr(sys, "argv", ["run_experiment.py", "capy-weights", "capy-weights"])

    with pytest.raises(ValueError, match="Invalid experiment inputs"):
        run_experiment.main()

    assert len(calls) == 1


def test_missing_stochastic_source_prevents_earlier_computation(monkeypatch):
    monkeypatch.setattr(
        compare_capy_weights,
        "run_capy_weight_comparison",
        lambda *args: pytest.fail("Missing stochastic source must fail before any computation"),
    )
    monkeypatch.setattr(sys, "argv", ["run_experiment.py", "capy-weights", "stochastic"])

    with pytest.raises(SystemExit) as error:
        run_experiment.main()

    assert error.value.code == 2


@pytest.mark.parametrize("command", [run_experiment, make_figures])
def test_synthetic_commands_ignore_unused_configuration(monkeypatch, tmp_path, command):
    from experiments.grid_configurations import grid_reference_scores, plot_grid_reference_scores

    calls = []
    monkeypatch.setattr(
        grid_reference_scores, "save_grid_reference_scores", lambda *args: calls.append(args)
    )
    monkeypatch.setattr(
        plot_grid_reference_scores, "plot_grid_reference_scores", lambda *args: calls.append(args)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            command.__name__,
            "grid-reference-scores",
            "--config",
            str(tmp_path / "absent.yaml"),
            "--data-directory",
            str(tmp_path),
        ],
    )

    command.main()

    assert len(calls) == 1
    assert calls[0][0] == tmp_path / "experiments/grid_configurations/grid_reference_scores"


def test_dispersion_default_stays_separate_from_shared_national_configuration(monkeypatch):
    from experiments.neighborhood_change import observed_dispersion

    calls = []
    monkeypatch.setattr(
        observed_dispersion, "run_observed_dispersion", lambda *args: calls.append(args)
    )
    monkeypatch.setattr(
        compare_capy_weights, "run_capy_weight_comparison", lambda *args: calls.append(args)
    )
    monkeypatch.setattr(
        sys, "argv", ["run_experiment.py", "capy-weights", "dispersion", "capy-weights"]
    )

    run_experiment.main()

    assert [args[0].study_area_type for args in calls] == ["cbsa", "max_city", "cbsa"]
    assert calls[0][2] == calls[2][2]
    assert calls[1][2] == Path(run_experiment.__file__).resolve().parents[1] / (
        "results/experiments/neighborhood_change"
    )
