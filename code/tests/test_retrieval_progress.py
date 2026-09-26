"""Progress follows completed work without changing retrieval results or downloaded bytes."""

from io import StringIO
from threading import Event
from unittest.mock import MagicMock

import pytest
from capy_core.pipeline_config import RawDataSubdirectories
from capy_core.retrieve_data import http_transport
from capy_core.retrieve_data import retrieve_files as retrieval
from capy_core.retrieve_data.nhgis.retrieve_extract import PendingNhgisExtract
from capy_core.retrieve_data.raw_file_requests import PublicFileRequest, RawFileFormat
from capy_core.retrieve_data.retrieve_raw_file import FailedFile, PendingFile, ReadyFile
from capy_core.stage_files import stage_file
from tqdm import tqdm


def test_progress_advances_before_slow_first_file_but_results_keep_order(
    tmp_path, monkeypatch, capsys
):
    later_file_reported = Event()
    outcomes = [
        ReadyFile("first.csv"),
        FailedFile("second.csv", "Download failed"),
        PendingFile("third.csv", PendingNhgisExtract(extract_id=12, status="queued")),
    ]
    requests = [
        PublicFileRequest(
            destination_relative_path=outcome.destination_relative_path,
            url="https://example.org/table.csv",
            file_format=RawFileFormat.CSV,
        )
        for outcome in outcomes
    ]

    def retrieve(request, **kwargs):
        if request.destination_relative_path == "first.csv":
            assert later_file_reported.wait(timeout=5), "Progress waited for the first file"
        return next(
            outcome
            for outcome in outcomes
            if outcome.destination_relative_path == request.destination_relative_path
        )

    class FileProgress(tqdm):
        def update(self, n=1):
            updated = super().update(n)
            later_file_reported.set()
            return updated

    monkeypatch.setattr(retrieval, "retrieve_raw_file", retrieve)
    with FileProgress(total=3, file=StringIO()) as progress:
        results = retrieval.retrieve_files_in_parallel(
            requests, tmp_path, False, 2, RawDataSubdirectories(), progress
        )

    assert results == outcomes
    assert progress.n == 2  # Pending files advance progress only after retries finish.
    output = capsys.readouterr().out
    assert "Failed: second.csv: Download failed" in output
    assert "Pending: third.csv (extract 12)" in output


@pytest.mark.parametrize(
    "headers,expected_total",
    [
        ({"Content-Length": "7"}, 7),
        ({}, None),
        ({"Content-Length": "20", "Content-Encoding": "gzip"}, None),
    ],
)
def test_download_progress_counts_bytes_without_exposing_urls(
    tmp_path, monkeypatch, headers, expected_total
):
    display = StringIO()
    response = MagicMock(status_code=200, headers=headers)
    response.__enter__.return_value = response
    response.iter_content.return_value = iter((b"abc", b"defg"))
    progress = tqdm(file=display, disable=False)
    progress_factory = MagicMock(return_value=progress)
    monkeypatch.setattr(http_transport, "tqdm", progress_factory)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: response)

    with stage_file(tmp_path) as temporary_path:
        http_transport.download_file(
            "https://example.org/file?key=private-key",
            temporary_path,
            download_label="population_reference_tables/census_working_paper_56_1990_tableA-01.xlsx",
        )
        assert temporary_path.read_bytes() == b"abcdefg"

    assert progress.n == 7
    assert progress_factory.call_args.kwargs["total"] == expected_total
    assert "tableA-01.xlsx" in progress_factory.call_args.kwargs["desc"]
    assert "private-key" not in str(progress_factory.call_args)
    assert "private-key" not in display.getvalue()


def test_interrupt_cancels_queued_downloads(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    release_worker = Event()
    worker_started = Event()
    started_paths = []
    pool = ThreadPoolExecutor(max_workers=1)
    original_shutdown = pool.shutdown

    def shutdown(wait=True, *, cancel_futures=False):
        # Release the active worker only after shutdown has handled the queue.
        original_shutdown(wait=False, cancel_futures=cancel_futures)
        release_worker.set()
        if wait:
            original_shutdown(wait=True)

    def retrieve(request, **kwargs):
        started_paths.append(request.destination_relative_path)
        worker_started.set()
        assert release_worker.wait(timeout=5)
        return ReadyFile(request.destination_relative_path)

    def interrupt(futures):
        assert worker_started.wait(timeout=5)
        raise KeyboardInterrupt

    requests = [
        PublicFileRequest(
            destination_relative_path=f"file_{number}.csv",
            url="https://example.org/data.csv",
            file_format=RawFileFormat.CSV,
        )
        for number in range(5)
    ]
    monkeypatch.setattr(pool, "shutdown", shutdown)
    monkeypatch.setattr(retrieval, "ThreadPoolExecutor", lambda **kwargs: pool)
    monkeypatch.setattr(retrieval, "retrieve_raw_file", retrieve)
    monkeypatch.setattr(retrieval, "as_completed", interrupt)

    with tqdm(file=StringIO()) as progress, pytest.raises(KeyboardInterrupt):
        retrieval.retrieve_files_in_parallel(
            requests, tmp_path, False, 1, RawDataSubdirectories(), progress
        )

    assert started_paths == ["file_0.csv"]
