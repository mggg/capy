"""Check command ordering, validation, and the boundary between computation and drawing."""

import sys

import make_figures
import pytest
from national_figures import plot_national_results


def test_figure_command_preserves_order_and_shared_paths(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        plot_national_results, "plot_national_figures", lambda *args: calls.append(args)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "make_figures.py",
            "national",
            "national",
            "--output-directory",
            str(tmp_path / "images"),
            "--data-directory",
            str(tmp_path / "results"),
        ],
    )

    make_figures.main()

    assert len(calls) == 2
    assert (
        calls[0][1:]
        == calls[1][1:]
        == (
            tmp_path / "images/national",
            tmp_path / "results/national/processed_data/history/CBSA20",
        )
    )


@pytest.mark.parametrize("arguments", [["national", "unknown"], ["national", "--plot-only"]])
def test_figure_command_rejects_invalid_arguments_before_drawing(monkeypatch, arguments):
    calls = []
    monkeypatch.setattr(
        plot_national_results, "plot_national_figures", lambda *args: calls.append(args)
    )
    monkeypatch.setattr(sys, "argv", ["make_figures.py", *arguments])

    with pytest.raises(SystemExit) as error:
        make_figures.main()

    assert error.value.code == 2
    assert not calls


def test_figure_command_stops_at_first_failure(monkeypatch):
    calls = []

    def fail_to_plot(*args):
        calls.append(args)
        raise FileNotFoundError("Missing saved metric table")

    monkeypatch.setattr(plot_national_results, "plot_national_figures", fail_to_plot)
    monkeypatch.setattr(sys, "argv", ["make_figures.py", "national", "national"])

    with pytest.raises(FileNotFoundError, match="Missing saved metric table"):
        make_figures.main()

    assert len(calls) == 1


def test_preparation_routes_plot_inputs_and_finished_tables_to_separate_custom_roots(
    monkeypatch, tmp_path
):
    import run_experiment
    from national_figures import prepare_ranked_table, prepare_score_ranks

    rank_calls = []
    table_calls = []
    monkeypatch.setattr(
        prepare_score_ranks, "prepare_score_rank_data", lambda *args: rank_calls.append(args)
    )
    monkeypatch.setattr(
        prepare_ranked_table,
        "prepare_ranked_population_table",
        lambda *args: table_calls.append(args),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_experiment.py",
            "score-ranks",
            "ranked-population-table",
            "--data-directory",
            str(tmp_path),
        ],
    )

    run_experiment.main()

    assert rank_calls[0][2:] == (
        tmp_path / "national/processed_data/score_ranks/CBSA20",
        tmp_path / "national/tables/score_ranks/CBSA20",
    )
    assert table_calls[0][2] == tmp_path / "national/tables/ranked_population_table/CBSA20"
