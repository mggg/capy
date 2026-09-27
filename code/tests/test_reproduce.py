"""Stage selection, execution order, and failures at the replication command line."""

from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
import reproduce
from capy_core.assign_study_areas.study_area_columns import MembershipColumn


@pytest.fixture
def pipeline_calls(tmp_path, monkeypatch):
    config_path = tmp_path / "run.yaml"
    config_path.write_text("offline: false\n")
    monkeypatch.setattr("sys.argv", ["reproduce.py", "--config", str(config_path)])

    calls = Mock()
    calls.retrieve_raw_data.return_value = SimpleNamespace(complete=True, file_results=[])
    calls.process_population_tables.return_value = []
    calls.assign_study_areas.return_value = pd.DataFrame({MembershipColumn.STATUS: ["assigned"]})
    calls.build_graph_archives.return_value = pd.DataFrame({MembershipColumn.STATUS: ["ready"]})
    monkeypatch.setattr(reproduce, "build_graph_archives", calls.build_graph_archives)
    monkeypatch.setattr(reproduce, "retrieve_raw_data", calls.retrieve_raw_data)
    monkeypatch.setattr(reproduce, "process_population_tables", calls.process_population_tables)
    monkeypatch.setattr(reproduce, "join_geography_tables", calls.join_geography_tables)
    monkeypatch.setattr(reproduce, "assign_study_areas", calls.assign_study_areas)
    return calls


@pytest.mark.parametrize(
    "stages,expected_calls",
    [
        (
            [],
            [
                "retrieve_raw_data",
                "process_population_tables",
                "join_geography_tables",
                "assign_study_areas",
                "build_graph_archives",
            ],
        ),
        (["build-graphs"], ["build_graph_archives"]),
        (["retrieve"], ["retrieve_raw_data"]),
        (["process-population"], ["process_population_tables"]),
        (["join-geographies"], ["join_geography_tables"]),
        (["assign-study-areas"], ["assign_study_areas"]),
        (
            ["join-geographies", "process-population", "join-geographies"],
            ["process_population_tables", "join_geography_tables"],
        ),
    ],
)
def test_selected_stages_run_once_in_pipeline_order(
    pipeline_calls, monkeypatch, stages, expected_calls
):
    import sys

    monkeypatch.setattr(sys, "argv", [*sys.argv, *stages])

    assert reproduce.main() == 0
    assert [call[0] for call in pipeline_calls.mock_calls] == expected_calls
    configs = [call.args[0] for call in pipeline_calls.mock_calls]
    assert all(config is configs[0] for config in configs)


@pytest.mark.parametrize("stages", [["unknown"], ["--stages", "retrieve"]])
def test_invalid_stage_arguments_fail_before_running(pipeline_calls, monkeypatch, stages):
    import sys

    monkeypatch.setattr(sys, "argv", [*sys.argv, *stages])

    with pytest.raises(SystemExit) as failure:
        reproduce.main()

    assert failure.value.code == 2
    assert not pipeline_calls.mock_calls


def test_incomplete_retrieval_stops_before_processing(pipeline_calls, capsys):
    pipeline_calls.retrieve_raw_data.return_value = SimpleNamespace(complete=False, file_results=[])

    assert reproduce.main() == 1
    assert [call[0] for call in pipeline_calls.mock_calls] == ["retrieve_raw_data"]
    assert "Retrieval incomplete" in capsys.readouterr().out


@pytest.mark.parametrize("error", [ValueError("invalid counts"), OSError("missing input")])
def test_stage_failure_reports_operation_and_stops_pipeline(pipeline_calls, capsys, error):
    pipeline_calls.process_population_tables.side_effect = error

    with pytest.raises(SystemExit) as failure:
        reproduce.main()

    assert failure.value.code == 1
    assert [call[0] for call in pipeline_calls.mock_calls] == [
        "retrieve_raw_data",
        "process_population_tables",
    ]
    assert f"Population processing could not complete: {error}" in capsys.readouterr().err


def test_offline_override_reaches_retrieval_in_full_pipeline(pipeline_calls, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", [*sys.argv, "--offline"])

    assert reproduce.main() == 0
    assert pipeline_calls.retrieve_raw_data.call_args.args[0].offline is True
    pipeline_calls.assign_study_areas.assert_called_once()
