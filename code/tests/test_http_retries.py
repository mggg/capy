"""Rate-limited downloads wait and retry without saving error responses or partial files."""

import io
import zipfile
from email.utils import formatdate
from unittest.mock import Mock

import pytest
import requests
from capy_core.retrieve_data import http_transport
from capy_core.retrieve_data.raw_file_requests import PublicFileRequest, RawFileFormat
from capy_core.retrieve_data.retrieval_config import RawDataSubdirectories
from capy_core.retrieve_data.retrieve_raw_file import FailedFile, ReadyFile, retrieve_raw_file


class Response:
    def __init__(self, status_code, headers=None, content=b"name,population\nexample,12\n"):
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def iter_content(self, size):
        assert self.status_code == 200, "An error response must never be saved"
        yield self.content


@pytest.mark.parametrize(
    "retry_after,expected_wait",
    [
        ("7", 7),
        (formatdate(1060, usegmt=True), 60),
        (formatdate(900, usegmt=True), 0),
        (None, 30),
        ("invalid", 30),
        ("-1", 30),
    ],
)
def test_rate_limit_wait_closes_response_then_downloads_once(
    tmp_path, monkeypatch, capsys, retry_after, expected_wait
):
    limited = Response(429, {"Retry-After": retry_after})
    success = Response(200)
    get = Mock(side_effect=[limited, success])

    def wait(seconds):
        assert limited.closed
        assert not success.closed
        assert seconds == expected_wait

    sleep = Mock(side_effect=wait)
    monkeypatch.setattr(http_transport.requests, "get", get)
    monkeypatch.setattr(http_transport.time, "sleep", sleep)
    monkeypatch.setattr(http_transport.time, "time", lambda: 1000)
    request = PublicFileRequest(
        destination_relative_path="tables/example.csv",
        file_format=RawFileFormat.CSV,
        url="https://example.org/private-key",
    )

    result = retrieve_raw_file(request, tmp_path, False, RawDataSubdirectories())

    assert result == ReadyFile(request.destination_relative_path)
    assert (tmp_path / request.destination_relative_path).read_bytes() == (
        b"name,population\nexample,12\n"
    )
    assert get.call_count == 2
    sleep.assert_called_once_with(expected_wait)
    assert success.closed
    output = capsys.readouterr().err
    assert "retry 1/3" in output
    assert "private-key" not in output


@pytest.mark.parametrize(
    "status_code,attempts,waits", [(429, 4, [30, 60, 120]), (404, 1, []), (503, 1, [])]
)
def test_retry_limit_and_other_errors_leave_no_file(
    tmp_path, monkeypatch, status_code, attempts, waits
):
    responses = [Response(status_code) for _ in range(attempts)]
    get = Mock(side_effect=responses)
    sleep = Mock()
    monkeypatch.setattr(http_transport.requests, "get", get)
    monkeypatch.setattr(http_transport.time, "sleep", sleep)
    request = PublicFileRequest(
        destination_relative_path="tables/example.csv",
        file_format=RawFileFormat.CSV,
        url="https://example.org/data",
    )

    result = retrieve_raw_file(request, tmp_path, False, RawDataSubdirectories())

    assert result == FailedFile(
        request.destination_relative_path, f"Provider returned HTTP {status_code}"
    )
    assert get.call_count == attempts
    assert [call.args[0] for call in sleep.call_args_list] == waits
    assert all(response.closed for response in responses)
    assert not any(path.is_file() for path in tmp_path.rglob("*"))


@pytest.mark.parametrize("failure_stage", ["connect", "body", "length"])
@pytest.mark.parametrize("recovers", [True, False])
def test_public_archive_transfer_retries_from_scratch(
    tmp_path, monkeypatch, capsys, failure_stage, recovers
):
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("population.csv", "population\n10\n")
    content = archive_bytes.getvalue()

    class BrokenResponse(Response):
        def iter_content(self, size):
            yield content[:10]
            if failure_stage == "body":
                raise requests.exceptions.ChunkedEncodingError("private-key")

    attempts = 2 if recovers else 5
    failures = [
        requests.ConnectionError("private-key")
        if failure_stage == "connect"
        else BrokenResponse(200, {"Content-Length": str(len(content))})
        for _ in range(attempts - int(recovers))
    ]
    responses = failures + ([Response(200, content=content)] if recovers else [])
    get = Mock(side_effect=responses)
    waits = []

    def wait(seconds):
        assert not list(tmp_path.rglob(".retrieval-*"))
        assert not (tmp_path / "population.zip").exists()
        waits.append(seconds)

    monkeypatch.setattr(http_transport.requests, "get", get)
    monkeypatch.setattr(http_transport.time, "sleep", wait)
    request = PublicFileRequest(
        destination_relative_path="population.zip",
        file_format=RawFileFormat.ZIP_ARCHIVE,
        url="https://example.org/private-key/data.zip",
    )

    result = retrieve_raw_file(request, tmp_path, False, RawDataSubdirectories())

    assert get.call_count == attempts
    assert waits == ([2] if recovers else [2, 4, 8, 10])
    assert all(response.closed for response in responses if isinstance(response, Response))
    assert "private-key" not in capsys.readouterr().err
    if recovers:
        assert isinstance(result, ReadyFile)
        assert (tmp_path / "population.zip").read_bytes() == content
    else:
        assert isinstance(result, FailedFile)
        assert "private-key" not in result.error_message
        assert not any(path.is_file() for path in tmp_path.rglob("*"))
