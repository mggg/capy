"""Keep numerical execution and figure rendering independent at the command boundary."""

import sys

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
