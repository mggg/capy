"""Raw-file retrieval, provider failures, and resumable NHGIS extraction."""

import json
from unittest.mock import Mock

import pytest
import requests
from capy_core.geography_types import GeographyLevel
from capy_core.pipeline_config import PipelineConfig, RawDataSubdirectories
from capy_core.retrieve_data.http_transport import (
    DataProviderError,
    download_file,
)
from capy_core.retrieve_data.prepare_file_requests import (
    build_raw_file_requests,
    select_raw_file_requests,
)
from capy_core.retrieve_data.raw_file_requests import (
    CensusDataset,
    CensusFileRequest,
    PublicFileRequest,
    RawFileFormat,
)
from capy_core.retrieve_data.retrieve_files import retrieve_files
from capy_core.retrieve_data.retrieve_raw_file import (
    FailedFile,
    ReadyFile,
    retrieve_raw_file,
)
from capy_core.stage_files import stage_file


def build_census_request(path="census/state.json"):
    return CensusFileRequest(
        destination_relative_path=path,
        census_year=2020,
        dataset=CensusDataset.PL_94_171,
        variables="NAME,P1_001N",
        geography_level=GeographyLevel.COUNTY,
        state_code="01",
    )


def write_population(path, state="01"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [["NAME", "P1_001N", "state", "county"], ["Autauga County", "58805", state, "001"]],
            indent=2,
        )
        + "\n"
    )


def test_failed_file_does_not_hide_independent_success(tmp_path):
    good = build_census_request()
    missing = build_census_request("missing.json")
    write_population(tmp_path / "raw" / good.destination_relative_path)
    config = PipelineConfig(raw_data_directory="raw", offline=True)
    result = retrieve_files(config, tmp_path, [good, missing])
    assert not result.complete
    assert [type(item) for item in result.file_results] == [ReadyFile, FailedFile]
    assert isinstance(result.file_results[1], FailedFile)
    assert result.file_results[1].destination_relative_path == "missing.json"
    assert "missing in offline mode" in result.file_results[1].error_message
    assert not (tmp_path / "raw/missing.json").exists()
    assert not list((tmp_path / "raw").rglob(".retrieval-*"))


def test_programming_error_is_not_reported_as_a_failed_download(tmp_path, monkeypatch):
    def broken_file_check(*args):
        raise TypeError("incorrect internal argument")

    request = build_census_request()
    write_population(tmp_path / request.destination_relative_path)
    monkeypatch.setattr(
        "capy_core.retrieve_data.retrieve_raw_file.check_raw_file", broken_file_check
    )

    with pytest.raises(TypeError, match="incorrect internal argument"):
        retrieve_raw_file(request, tmp_path, True, RawDataSubdirectories())


def test_invalid_provider_length_does_not_expose_header_contents(tmp_path, monkeypatch):
    response = Response()
    response.headers["Content-Length"] = "private-provider-value"
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: response)

    with (
        stage_file(tmp_path) as staged,
        pytest.raises(DataProviderError, match="invalid Content-Length") as failure,
    ):
        download_file("https://example.org/data", staged)

    assert "private-provider-value" not in str(failure.value)


class Response:
    status_code = 200

    def __init__(self):
        self.headers = {"Content-Length": "20"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, size):
        yield b"short"


def test_partial_download_is_rejected_and_discarded(tmp_path, monkeypatch):
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: Response())
    with (
        pytest.raises(DataProviderError, match="Content-Length"),
        stage_file(tmp_path) as staged,
    ):
        download_file("https://example.org/a", staged)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("content", ["", "[]", '[["name","population"],["example"]]'])
def test_basic_census_checks_reject_empty_or_malformed_existing_tables(tmp_path, content):
    file_request = build_census_request()
    destination = tmp_path / file_request.destination_relative_path
    destination.parent.mkdir(parents=True)
    destination.write_text(content)

    result = retrieve_raw_file(file_request, tmp_path, True, directories=RawDataSubdirectories())

    assert isinstance(result, FailedFile)
    assert destination.read_text() == content


def test_raw_file_definitions_and_geographic_coverage():
    with pytest.raises(ValueError):
        build_census_request("../outside.json")
    file_requests = build_raw_file_requests(PipelineConfig())
    assert all(isinstance(request.file_format, RawFileFormat) for request in file_requests)
    groups = {
        tuple(file_request.destination_relative_path.split("/")[1:4])
        for file_request in file_requests
        if file_request.destination_relative_path.startswith("census/")
    }
    assert len(groups) == 676
    assert all(
        sum(
            census_year == str(year) and level == resolution for census_year, level, state in groups
        )
        == 52
        for year in (2000, 2010, 2020)
        for resolution in ("counties", "tracts", "block_groups", "blocks")
    )
    assert (
        sum(
            file_request.destination_relative_path.startswith("census_1980_stf1a/")
            for file_request in file_requests
        )
        == 51
    )
    assert len(file_requests) == 1275
    destinations = [request.destination_relative_path for request in file_requests]
    assert destinations == sorted(destinations)

    census_requests = [
        request for request in file_requests if isinstance(request, CensusFileRequest)
    ]
    assert all(isinstance(request.dataset, CensusDataset) for request in census_requests)
    assert {
        (request.census_year, request.geography_level)
        for request in census_requests
        if request.dataset == CensusDataset.SUMMARY_FILE_1
    } == {(2000, GeographyLevel.BLOCK_GROUP)}


def test_selection_preserves_order_and_rejects_duplicate_or_unmatched_destinations():
    first_request = build_census_request("census/first.json")
    second_request = build_census_request("census/second.json")
    requests = [first_request, second_request]

    assert select_raw_file_requests(requests, ("census/*", "census/first.json")) == requests
    with pytest.raises(ValueError, match="unique destinations"):
        select_raw_file_requests([first_request, first_request], ("*",))
    with pytest.raises(ValueError, match="No defined files match"):
        select_raw_file_requests(requests, ("missing/*",))


def test_invalid_download_is_not_published(tmp_path, monkeypatch):
    class HtmlResponse(Response):
        def __init__(self):
            self.headers = {}

        def iter_content(self, size):
            yield b"<html>service error</html>"

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: HtmlResponse())
    file_request = PublicFileRequest(
        destination_relative_path="broken.zip",
        file_format=RawFileFormat.ZIP_ARCHIVE,
        url="https://example.org/broken.zip",
    )
    raw = tmp_path / "raw"
    result = retrieve_raw_file(
        file_request, raw, offline=False, directories=RawDataSubdirectories()
    )
    assert isinstance(result, FailedFile)
    assert not (raw / file_request.destination_relative_path).exists()
    assert not list(raw.glob(".retrieval-*"))


@pytest.mark.parametrize(
    "error_type,expected_attempts",
    [(requests.ConnectionError, 5), (requests.Timeout, 5), (requests.exceptions.SSLError, 1)],
)
def test_transport_errors_retry_only_transient_failures_without_exposing_credentials(
    tmp_path, monkeypatch, error_type, expected_attempts
):
    get = Mock(side_effect=error_type("https://example.org/?key=private-key"))
    monkeypatch.setattr("requests.get", get)
    monkeypatch.setattr(
        "capy_core.retrieve_data.retrieve_raw_file.time.sleep", lambda seconds: None
    )
    raw = tmp_path / "raw"
    result = retrieve_raw_file(
        build_census_request(), raw, False, directories=RawDataSubdirectories()
    )
    assert isinstance(result, FailedFile)
    assert "private-key" not in result.error_message
    assert error_type.__name__ in result.error_message
    assert get.call_count == expected_attempts


def test_http_census_response_preserves_bytes_and_existing_files(tmp_path, monkeypatch):
    content = '[["NAME","state"],\r\n ["Doña Ana","35"]]'.encode()

    class CensusResponse(Response):
        def __init__(self):
            self.headers = {"Content-Length": str(len(content))}

        def iter_content(self, size):
            yield content[:25]
            yield content[25:]

    calls = []

    def get(url, *, params, **kwargs):
        calls.append(params)
        return CensusResponse()

    monkeypatch.setenv("CENSUS_API_KEY", "private-key")
    monkeypatch.setattr("requests.get", get)
    raw = tmp_path / "raw"
    file_request = build_census_request()
    result = retrieve_raw_file(file_request, raw, False, directories=RawDataSubdirectories())

    assert isinstance(result, ReadyFile)
    destination = raw / file_request.destination_relative_path
    assert destination.read_bytes() == content
    assert calls == [
        {"get": "NAME,P1_001N", "for": "county:*", "in": "state:01", "key": "private-key"}
    ]

    existing_content = json.dumps(json.loads(content), indent=2).encode("utf-8")
    destination.write_bytes(existing_content)
    repeated = retrieve_raw_file(file_request, raw, True, directories=RawDataSubdirectories())

    assert isinstance(repeated, ReadyFile)
    assert destination.read_bytes() == existing_content
    assert len(calls) == 1


@pytest.mark.parametrize(
    "content",
    [
        b"<html>service error</html>",
        b'[["NAME","state"],["incomplete"]]',
        b'[["population"],[NaN]]',
        b'[["population"],[Infinity]]',
        b'[["population"],[-Infinity]]',
        b'[["population"],[1e999]]',
    ],
)
def test_invalid_census_download_is_rejected_before_publication(tmp_path, monkeypatch, content):
    class CensusResponse(Response):
        def __init__(self):
            self.headers = {"Content-Length": str(len(content))}

        def iter_content(self, size):
            yield content

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: CensusResponse())
    raw = tmp_path / "raw"
    file_request = build_census_request()

    result = retrieve_raw_file(file_request, raw, False, directories=RawDataSubdirectories())

    assert isinstance(result, FailedFile)
    assert not (raw / file_request.destination_relative_path).exists()
    assert not list(raw.rglob(".retrieval-*"))
