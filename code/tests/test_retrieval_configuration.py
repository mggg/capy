"""Complete run settings control input locations and command defaults."""

import hashlib
import os
from pathlib import Path

import pytest
from capy_core.pipeline_config import (
    PipelineConfig,
    RawDataSubdirectories,
    load_configuration,
)
from capy_core.retrieve_data.prepare_file_requests import build_raw_file_requests
from capy_core.retrieve_data.retrieve_files import retrieve_files
from capy_core.retrieve_data.retrieve_raw_file import ReadyFile


@pytest.mark.parametrize("absolute_path", [False, True])
def test_env_file_reaches_workers_without_replacing_shell_variables(
    tmp_path, monkeypatch, absolute_path
):
    import reproduce

    # Keep variables loaded by python-dotenv local to this test.
    monkeypatch.setattr(os, "environ", os.environ.copy())
    monkeypatch.delenv("IPUMS_API_KEY", raising=False)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    monkeypatch.setenv("CENSUS_API_KEY", "shell-census-key")
    env_path = tmp_path / ".env"
    env_path.write_text('export IPUMS_API_KEY="file-ipums-key"\nCENSUS_API_KEY=file-census-key\n')
    configured_path = env_path if absolute_path else Path(".env")
    config_path = tmp_path / "run.yaml"
    config_path.write_text(
        f"env_file: {configured_path}\nfile_path_patterns: ['census/2020/tracts/10/state.json']\n"
    )
    config = load_configuration(config_path)
    assert config.env_file == configured_path
    assert "IPUMS_API_KEY" not in os.environ

    observed_credentials = []

    def retrieve_file(request, **kwargs):
        observed_credentials.append((os.environ["IPUMS_API_KEY"], os.environ["CENSUS_API_KEY"]))
        return ReadyFile(request.destination_relative_path)

    monkeypatch.setattr("capy_core.retrieve_data.retrieve_files.retrieve_raw_file", retrieve_file)
    monkeypatch.setattr(reproduce, "__file__", str(tmp_path / "code/reproduce.py"))
    monkeypatch.setattr("sys.argv", ["reproduce.py", "--config", str(config_path)])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert reproduce.main() == 0
    assert observed_credentials == [("file-ipums-key", "shell-census-key")]


@pytest.mark.parametrize("offline", [False, True])
def test_configured_missing_env_file_is_required_only_for_online_retrieval(tmp_path, offline):
    config = PipelineConfig(env_file=Path("missing.env"), offline=offline)

    if offline:
        assert retrieve_files(config, tmp_path, []).complete
    else:
        with pytest.raises(FileNotFoundError, match="missing.env"):
            retrieve_files(config, tmp_path, [])


def test_unconfigured_env_file_is_not_discovered(tmp_path, monkeypatch):
    monkeypatch.delenv("IPUMS_API_KEY", raising=False)
    (tmp_path / ".env").write_text("IPUMS_API_KEY=unused-key\n")
    assert retrieve_files(PipelineConfig(), tmp_path, []).complete
    assert "IPUMS_API_KEY" not in os.environ


def test_positive_download_limit_has_no_fixed_ceiling_and_rejects_zero():
    config = PipelineConfig(max_parallel_downloads=32)
    config.max_parallel_downloads = 64

    with pytest.raises(ValueError):
        config.max_parallel_downloads = 0

    assert config.max_parallel_downloads == 64


@pytest.mark.parametrize(
    "content,expected_message",
    [
        ("max_parallel_downloads: 0\n", "max_parallel_downloads"),
        ("nhgis_retry_interval_seconds: 0\n", "nhgis_retry_interval_seconds"),
        ("nhgis_max_wait_minutes: -1\n", "nhgis_max_wait_minutes"),
        ("unknown_setting: true\n", "unknown_setting"),
        ("census_geography_years: [2020\n", "line"),
    ],
)
def test_command_reports_configuration_file_and_invalid_setting(
    tmp_path, monkeypatch, capsys, content, expected_message
):
    import reproduce

    config = tmp_path / "invalid.yaml"
    config.write_text(content)
    monkeypatch.setattr("sys.argv", ["reproduce.py", "--config", str(config)])

    with pytest.raises(SystemExit) as failure:
        reproduce.main()

    message = capsys.readouterr().err
    assert failure.value.code == 1
    assert str(config) in message
    assert expected_message in message
    assert "Traceback" not in message


def test_yaml_controls_every_raw_input_family(tmp_path):
    config_path = tmp_path / "replication.yaml"
    config_path.write_text(
        """raw_data_directory: datasets/raw
raw_data_subdirectories:
  census_population_tables: tables/census
  nhgis_population_and_boundaries: historical/nhgis
  census_boundary_files: boundaries/tiger
  original_1980_boundary_files: historical/tiger_1992
  original_1990_block_references: historical/blocks_1990
  population_reference_tables: references/populations
  metro_membership_tables: references/metros
  saved_nhgis_requests: .status/nhgis
"""
    )
    config = load_configuration(config_path)
    requests = build_raw_file_requests(config)
    destinations = {request.destination_relative_path for request in requests}

    assert {
        "tables/census/2010/blocks/10/state.json",
        "historical/nhgis/1980/tracts/population.zip",
        "boundaries/tiger/2020/tracts/tl_2020_10_tract.zip",
        "historical/tiger_1992/12107.zip",
        "historical/blocks_1990/disc1.zip",
        "references/populations/2020_states.json",
        "references/populations/census_state_population_totals_2020_release.csv",
        "references/populations/census_working_paper_56_1990_tableE-01.xlsx",
        "references/metros/list1_march_2020.xls",
    } <= destinations
    assert all(
        path.startswith(("tables/", "historical/", "boundaries/", "references/"))
        for path in destinations
    )
    assert not (tmp_path / "datasets").exists()


@pytest.mark.parametrize("directory", ["../outside", "/outside", ".", "folder/../outside"])
def test_raw_subdirectories_reject_ambiguous_or_escaping_paths(directory):
    with pytest.raises(ValueError):
        RawDataSubdirectories(census_population_tables=directory)


@pytest.mark.parametrize("use_cli_overrides", [False, True])
def test_commands_reuse_configured_folders_and_write_checksums(
    tmp_path, monkeypatch, use_cli_overrides
):
    import record_raw_checksums
    import reproduce

    payload = b'[["state","county","block"],["10","001","1000"]]\n'
    relative_path = "population/2010/blocks/10/state.json"
    existing_file = tmp_path / "custom/raw" / relative_path
    existing_file.parent.mkdir(parents=True)
    existing_file.write_bytes(payload)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    config = tmp_path / "run.yaml"
    configured_checksums = (
        "unused/checksums.sha256" if use_cli_overrides else "published/checksums.sha256"
    )
    config.write_text(
        f"""raw_data_directory: custom/raw
census_geography_years: [2010]
census_geography_levels: [blocks]
raw_data_subdirectories:
  census_population_tables: population
env_file: missing.env
offline: {str(not use_cli_overrides).lower()}
file_path_patterns: ['{relative_path}']
raw_checksums_file: {configured_checksums}
"""
    )
    # Give both entry points the same temporary repository root.
    monkeypatch.setattr(reproduce, "__file__", str(tmp_path / "code/reproduce.py"))
    monkeypatch.setattr(
        record_raw_checksums, "__file__", str(tmp_path / "code/record_raw_checksums.py")
    )
    monkeypatch.chdir(elsewhere)
    retrieval_args = ["reproduce.py", "--config", str(config)]
    if use_cli_overrides:
        retrieval_args += ["--offline"]
    monkeypatch.setattr("sys.argv", retrieval_args)

    assert reproduce.main() == 0
    assert (tmp_path / "custom/raw" / relative_path).read_bytes() == payload
    assert not (tmp_path / "custom/raw/population/2010/counties").exists()

    checksum_args = ["record_raw_checksums.py", "--config", str(config)]
    if use_cli_overrides:
        checksum_args += ["--output", "../published/checksums.sha256"]
    monkeypatch.setattr("sys.argv", checksum_args)
    record_raw_checksums.main()

    assert (tmp_path / "published/checksums.sha256").read_text() == (
        f"{hashlib.sha256(payload).hexdigest()}  {relative_path}\n"
    )
