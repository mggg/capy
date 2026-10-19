"""Retrieve statewide 2010 blocks using county codes read from Census tables."""

import json

import pytest
from national_pipeline.pipeline_config import (
    PipelineConfig,
    load_configuration,
)
from national_pipeline.retrieve_data.census.retrieve_tables import load_county_codes
from national_pipeline.retrieve_data.retrieve_files import retrieve_raw_data
from national_pipeline.retrieve_data.retrieve_raw_file import FailedFile, ReadyFile


@pytest.mark.parametrize("select_counties", [False, True])
def test_reusing_blocks_needs_no_unselected_county_table(tmp_path, select_counties):
    raw = tmp_path / "raw"
    block_path = "census/2010/blocks/10/state.json"
    block_file = raw / block_path
    block_file.parent.mkdir(parents=True, exist_ok=True)
    block_file.write_text(json.dumps([["state", "county", "block"], ["10", "001", "1000"]]))
    county_path = "census/2010/counties/10/state.json"
    patterns = (block_path, county_path) if select_counties else (block_path,)
    config = PipelineConfig(
        raw_data_directory=raw,
        file_path_patterns=patterns,
        offline=True,
    )

    result = retrieve_raw_data(config, tmp_path)

    assert ReadyFile(block_path) in result.file_results
    assert not (raw / county_path).exists()
    assert result.complete is not select_counties
    if select_counties:
        assert len(result.file_results) == 2
        assert any(
            isinstance(item, FailedFile) and item.destination_relative_path == county_path
            for item in result.file_results
        )
    else:
        assert result.file_results == (ReadyFile(block_path),)


def test_county_failure_does_not_stop_unrelated_downloads(tmp_path):
    independent = "population_reference_tables/2020_states.json"
    raw = tmp_path / "raw"
    existing = raw / independent
    existing.parent.mkdir(parents=True)
    contents = json.dumps([["NAME", "state"], ["Delaware", "10"]])
    existing.write_text(contents)
    config = PipelineConfig(
        raw_data_directory=tmp_path / "raw",
        file_path_patterns=("census/2010/blocks/10/*", independent),
        offline=True,
    )

    result = retrieve_raw_data(config, tmp_path)

    assert not result.complete
    assert {
        item.destination_relative_path
        for item in result.file_results
        if isinstance(item, FailedFile)
    } == {
        "census/2010/counties/10/state.json",
        "census/2010/blocks/10/state.json",
    }
    assert ReadyFile(independent) in result.file_results
    assert existing.read_text() == contents


@pytest.mark.parametrize("census_directory", ["census", "tables/census"])
@pytest.mark.parametrize("include_counties", [False, True])
def test_download_uses_counties_from_the_selected_states_2010_table(
    tmp_path, monkeypatch, include_counties, census_directory
):
    calls = []
    county_table = [
        ["NAME", "state", "county"],
        ["Sussex", "10", "005"],
        ["New Castle", "10", "001"],
    ]
    block_table = [["state", "county", "tract", "block"], ["10", "001", "000100", "1000"]]

    class Response:
        status_code = 200

        def __init__(self, table):
            self.content = json.dumps(table).encode("utf-8")
            self.headers = {"Content-Length": str(len(self.content))}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_content(self, size):
            yield self.content

    def get(url, *, params, **kwargs):
        calls.append((url, params))
        return Response(county_table if params["for"] == "county:*" else block_table)

    monkeypatch.setenv("CENSUS_API_KEY", "test-key")
    monkeypatch.setattr("requests.get", get)
    patterns = [f"{census_directory}/2010/blocks/10/*"]
    if include_counties:
        patterns.append(f"{census_directory}/2010/counties/10/*")
    config_path = tmp_path / "run.yaml"
    config_path.write_text(
        f"raw_data_directory: {tmp_path / 'raw'}\n"
        f"raw_data_subdirectories:\n  census_population_tables: {census_directory}\n"
        f"file_path_patterns: {json.dumps(patterns)}\n"
    )
    config = load_configuration(config_path)

    result = retrieve_raw_data(config, tmp_path)

    assert result.complete
    assert len(calls) == 2
    assert all(url == "https://api.census.gov/data/2010/dec/pl" for url, params in calls)
    assert calls[0][1]["for"] == "county:*"
    assert calls[0][1]["in"] == "state:10"
    assert calls[1][1]["for"] == "block:*"
    assert calls[1][1]["in"] == "state:10 county:001,005 tract:*"
    assert len(result.file_results) == 2

    config.offline = True
    repeated = retrieve_raw_data(config, tmp_path)
    assert repeated.complete
    assert len(calls) == 2


@pytest.mark.parametrize(
    "rows",
    [
        [["09", "001"]],
        [["10", "1"]],
        [["10", "001"], ["10", "001"]],
        [["10", "001", "unexpected column"]],
        [],
    ],
)
def test_county_discovery_rejects_malformed_rows_or_invalid_county_codes(tmp_path, rows):
    path = tmp_path / "counties.json"
    path.write_text(json.dumps([["state", "county"], *rows]))
    with pytest.raises(ValueError):
        load_county_codes(path, "10")
