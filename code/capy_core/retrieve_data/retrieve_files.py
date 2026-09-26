"""Run the selected raw-file requests and report ready, pending, and failed raw files."""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

from capy_core.pipeline_config import PipelineConfig, RawDataSubdirectories

from .census.retrieve_tables import prepare_download_batches_with_2010_counties_first
from .prepare_file_requests import select_raw_file_requests
from .raw_file_requests import RawFileRequest
from .retrieve_raw_file import (
    FailedFile,
    FileRetrievalResult,
    PendingFile,
    ReadyFile,
    retrieve_raw_file,
)


@dataclass(frozen=True)
class RetrievalResult:
    """Results for requested files and any county tables needed to download 2010 blocks.

    file_results keeps the order of the retrieval batches, with required county tables first. Each
    entry identifies a ready file, an unfinished NHGIS request, or a failed retrieval.
    """

    file_results: tuple[FileRetrievalResult, ...]

    @property
    def complete(self) -> bool:
        """Whether every reported file is locally available and passed its basic format check."""
        return all(isinstance(result, ReadyFile) for result in self.file_results)


def retrieve_raw_data(
    config: PipelineConfig,
    repository: Path,
) -> RetrievalResult:
    """Select raw inputs from the versioned definitions and retrieve them.

    Args:
        config (PipelineConfig): Complete run settings, including selection, layout, and offline
            mode.
        repository (Path): Base for a relative raw-data directory.

    Returns:
        RetrievalResult: Outcomes for selected inputs and prerequisite county tables, each once.
            Failed prerequisites do not stop unrelated files.

    Raises:
        ValueError: Selections are invalid.
        OSError: Reading the configured env file or preparing directories fails.
    """
    selected_requests = select_raw_file_requests(config)

    return retrieve_files(config, repository, selected_requests)


def retrieve_files(
    config: PipelineConfig,
    repository: Path,
    file_requests: list[RawFileRequest],
) -> RetrievalResult:
    """Retrieve selected raw files, downloading required county tables before 2010 blocks.

    Each raw-data directory is used by one run at a time. Necessary county tables are retrieved
    before dependent 2010 block tables; files within each batch can be retrieved at the same time.
    A failed file does not stop unrelated files from being tried.

    Online runs load the configured env file into the process environment before starting workers.
    Existing environment variables take precedence. Offline runs do not read the env file.

    Args:
        config (PipelineConfig): Folder paths, env file, offline setting, and maximum number of
            simultaneous retrievals. The caller supplies the selected files separately.
        repository (Path): Repository directory, used as the base for relative configured paths.
        file_requests (list[RawFileRequest]): Selected raw inputs. The caller must already have
            checked that no two requests use the same destination filename.

    Returns:
        RetrievalResult: One outcome per selected input and any added county table. Required
            county tables appear first, and each batch keeps the original request order.

    Raises:
        ValueError: Settings or inputs are invalid.
        OSError: Reading the configured env file or preparing directories fails.

    Pending extracts are checked again after the initial batches, up to the configured wait limit.
    Completed files are not retried. Remaining pending and failed inputs make the run incomplete;
    a later run reuses their saved submissions. Checksums are recorded by a separate command.
    """
    if config.env_file is not None and not config.offline:
        with (repository / config.env_file).open(encoding="utf-8") as env_stream:
            load_dotenv(stream=env_stream, override=False)

    raw_data_directory = (repository / config.raw_data_directory).resolve()
    raw_data_directory.mkdir(parents=True, exist_ok=True)

    request_batches = prepare_download_batches_with_2010_counties_first(
        file_requests, raw_data_directory, config.raw_data_subdirectories
    )

    results = []
    with tqdm(
        total=sum(len(batch) for batch in request_batches),
        desc="Files processed",
        unit="file",
        position=0,
        dynamic_ncols=True,
        disable=None,
    ) as file_progress:
        for batch in request_batches:
            batch_results = retrieve_files_in_parallel(
                requests=batch,
                raw_data_directory=raw_data_directory,
                offline=config.offline,
                max_parallel_downloads=config.max_parallel_downloads,
                directories=config.raw_data_subdirectories,
                file_progress=file_progress,
            )
            results.extend(batch_results)

        requests_in_order = [request for batch in request_batches for request in batch]
        results = retry_pending_nhgis_files(
            requests_in_order, results, config, raw_data_directory, file_progress
        )

    return RetrievalResult(tuple(results))


def retrieve_files_in_parallel(
    requests: list[RawFileRequest],
    raw_data_directory: Path,
    offline: bool,
    max_parallel_downloads: int,
    directories: RawDataSubdirectories,
    file_progress: tqdm,
) -> list[FileRetrievalResult]:
    """Retrieve several files at a time and report individual failures without stopping the batch.

    Call this through retrieve_files() so required county tables are retrieved first. Progress
    advances for ready and failed files; pending files are counted when a retry finishes or the
    run stops waiting. Returned results retain request order. Each worker calls
    retrieve_raw_file(), which may retry a broken transfer. This function does not recheck pending
    extracts; retrieve_files() coordinates those later rounds. On interruption or an unexpected
    error, queued work is cancelled. Downloads already running are allowed to finish or fail
    before this function exits.

    Args:
        requests (list[RawFileRequest]): Selected inputs in definition order.
        raw_data_directory (Path): Directory containing the raw files for this run.
        offline (bool): Prevent provider requests while allowing local reuse.
        max_parallel_downloads (int): Maximum number of simultaneous retrievals.
        directories (RawDataSubdirectories): Configured folders beneath raw_data_directory.
        file_progress (tqdm): Shared file counter, opened and closed by retrieve_files().

    Returns:
        list[FileRetrievalResult]: One ready, pending, or failed result per requested file,
    in definition order.
    """
    worker = partial(
        retrieve_raw_file,
        raw_data_directory=raw_data_directory,
        offline=offline,
        directories=directories,
    )
    pool = ThreadPoolExecutor(max_workers=max_parallel_downloads)
    try:
        future_indexes = {
            pool.submit(worker, request): index for index, request in enumerate(requests)
        }
        results_by_index = {}
        for future in as_completed(future_indexes):
            result = future.result()
            results_by_index[future_indexes[future]] = result
            if not isinstance(result, PendingFile):
                file_progress.update(1)

            if isinstance(result, FailedFile):
                tqdm.write(
                    f"Failed: {result.destination_relative_path}: {result.error_message}",
                )
                sys.stdout.flush()
            elif isinstance(result, PendingFile):
                extract_id = result.pending_extract.extract_id
                tqdm.write(
                    f"Pending: {result.destination_relative_path} (extract {extract_id})",
                )
                sys.stdout.flush()

    finally:
        pool.shutdown(wait=True, cancel_futures=True)

    return [results_by_index[index] for index in range(len(requests))]


def retry_pending_nhgis_files(
    requests: list[RawFileRequest],
    results: list[FileRetrievalResult],
    config: PipelineConfig,
    raw_data_directory: Path,
    file_progress: tqdm,
) -> list[FileRetrievalResult]:
    """Recheck pending NHGIS extracts until ready, failed, or the configured wait expires.

    Saved extract numbers are reused on every attempt. Ready and failed files are left alone.
    Waiting starts after the initial retrieval batches, so other downloads can finish first. Each
    wait is capped by the time remaining. After that wait, the whole retry round is allowed to
    finish, including queued requests and downloads that start after the limit. No further round
    is scheduled once the time is used up. Ctrl-C interrupts the wait; saved submissions remain
    available for the next run.

    Args:
        requests (list[RawFileRequest]): Attempted inputs, in the same order as results.
        results (list[FileRetrievalResult]): Initial outcomes, left unchanged by this function.
        config (PipelineConfig): Retry interval, wait limit, and retrieval settings.
        raw_data_directory (Path): Resolved directory containing raw files and saved submissions.
        file_progress (tqdm): Shared counter; each pending file is counted once when finished.

    Returns:
        list[FileRetrievalResult]: Latest outcomes in the original order. Unfinished extracts
            remain PendingFile when the limit expires or retries are disabled.
    """
    updated_results = results.copy()
    pending_indexes = [
        index for index, result in enumerate(updated_results) if isinstance(result, PendingFile)
    ]
    deadline = time.monotonic() + config.nhgis_max_wait_minutes * 60

    while pending_indexes:
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            break

        wait_seconds = min(config.nhgis_retry_interval_seconds, remaining_seconds)
        tqdm.write(
            f"Waiting {wait_seconds:g} seconds before rechecking "
            f"{len(pending_indexes)} pending NHGIS extracts."
        )
        sys.stdout.flush()
        time.sleep(wait_seconds)

        retried_results = retrieve_files_in_parallel(
            requests=[requests[index] for index in pending_indexes],
            raw_data_directory=raw_data_directory,
            offline=config.offline,
            max_parallel_downloads=config.max_parallel_downloads,
            directories=config.raw_data_subdirectories,
            file_progress=file_progress,
        )
        for index, result in zip(pending_indexes, retried_results, strict=True):
            updated_results[index] = result

        pending_indexes = [
            index for index in pending_indexes if isinstance(updated_results[index], PendingFile)
        ]

    if pending_indexes:
        file_progress.update(len(pending_indexes))
        tqdm.write(f"Stopped waiting: {len(pending_indexes)} NHGIS extracts remain pending.")
        sys.stdout.flush()

    return updated_results
