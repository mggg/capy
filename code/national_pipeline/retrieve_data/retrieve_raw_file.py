"""Obtain a raw file through local reuse or its provider, then perform a basic file check."""

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile

from tqdm import tqdm

from national_pipeline.pipeline_config import RawDataSubdirectories
from national_pipeline.stage_files import stage_file

from .census.retrieve_tables import download_census_table
from .check_raw_files import check_existing_raw_file, check_raw_file
from .http_transport import DataProviderError, RetryableDownloadError, download_file
from .nhgis.retrieve_extract import (
    PendingNhgisExtract,
    load_matching_nhgis_submission,
    retrieve_nhgis_extract,
)
from .raw_file_requests import (
    CensusFileRequest,
    NhgisBoundaryFileRequest,
    NhgisTableFileRequest,
    RawFileRequest,
)


@dataclass(frozen=True)
class ReadyFile:
    """A locally available file that passed basic format checks, not yet population checks."""

    destination_relative_path: str


@dataclass(frozen=True)
class PendingFile:
    """A file NHGIS is still preparing; its saved request can be checked again on a retry."""

    destination_relative_path: str
    pending_extract: PendingNhgisExtract


@dataclass(frozen=True)
class FailedFile:
    """A file that could not be obtained or checked, with an error message explaining why."""

    destination_relative_path: str
    error_message: str


FileRetrievalResult = ReadyFile | PendingFile | FailedFile


def retrieve_raw_file(
    request: RawFileRequest,
    raw_data_directory: Path,
    offline: bool,
    directories: RawDataSubdirectories,
) -> FileRetrievalResult:
    """Find or retrieve one planned raw file and report whether it is ready, pending, or failed.

    An existing destination is checked first. If it is absent, contact the provider unless offline
    mode is enabled. Existing destinations are never overwritten, even when they fail a check.
    Downloads must pass the full basic format checks before becoming ready; existing files get
    the cheaper check_existing_raw_file(), which does not parse Census tables again. Saved NHGIS
    submissions must match the current request, including when reusing a local file. Files without
    submission records receive format checks only; their selections are not verified. Transient
    connection failures and incomplete transfers get up to five attempts, waiting 2, 4, 8, then 10
    seconds. Each attempt uses a fresh temporary file. Other errors are not retried.

    Args:
        request (RawFileRequest): Raw file to obtain and its provider details.
        raw_data_directory (Path): Directory containing raw files and NHGIS submission records.
        offline (bool): Permit local reuse but prevent provider requests.
        directories (RawDataSubdirectories): Configured folders beneath raw_data_directory.

    Returns:
        FileRetrievalResult: ReadyFile for a checked local file, PendingFile while NHGIS prepares
            its download, or FailedFile with a reason retrieval could not finish.

    These checks do not compare published checksums or validate population values. Expected
    file, format, and provider errors become failed-file results. Provider operations remove
    sensitive details before raising errors. Unexpected programming errors and interruptions
    pass back to the caller instead of being reported as ordinary failed downloads.
    """
    try:
        destination = raw_data_directory / request.destination_relative_path
        if not destination.resolve().is_relative_to(raw_data_directory.resolve()):
            raise ValueError("File destination escapes the raw data directory")

        if destination.exists():
            if isinstance(request, (NhgisTableFileRequest, NhgisBoundaryFileRequest)):
                load_matching_nhgis_submission(
                    request, raw_data_directory / directories.saved_nhgis_requests
                )

            check_existing_raw_file(destination, request.file_format)
            return ReadyFile(request.destination_relative_path)

        attempt = 1
        while True:
            try:
                return acquire_missing_file(
                    request=request,
                    destination=destination,
                    raw_data_directory=raw_data_directory,
                    offline=offline,
                    directories=directories,
                )
            except RetryableDownloadError as error:
                if attempt == 5:
                    raise

                wait_seconds = min(2**attempt, 10)
                tqdm.write(
                    f"Retrying {request.destination_relative_path} in {wait_seconds}s "
                    f"(attempt {attempt + 1}/5): {error}",
                    file=sys.stderr,
                )
                time.sleep(wait_seconds)
                attempt += 1

    except (ValueError, OSError, BadZipFile, DataProviderError) as error:
        return FailedFile(request.destination_relative_path, str(error))


def acquire_missing_file(
    request: RawFileRequest,
    destination: Path,
    raw_data_directory: Path,
    offline: bool,
    directories: RawDataSubdirectories,
) -> ReadyFile | PendingFile:
    """Obtain a missing file under a temporary name, check it, then give it its final filename.

    Temporary files are removed when this call ends without publication, whether a download fails,
    the user interrupts it, or NHGIS is still preparing the requested data.

    Args:
        request (RawFileRequest): Provider request and expected file format.
        destination (Path): Missing output file to create.
        raw_data_directory (Path): Raw-data root used to find required county tables and saved
            NHGIS submission records.
        offline (bool): Reject requests requiring network access.
        directories (RawDataSubdirectories): Configured folders beneath raw_data_directory.

    Returns:
        ReadyFile | PendingFile: File saved at its final path, or an NHGIS request that a retry
            can check again using its saved submission number.

    Raises:
        ValueError: Offline mode prevents the download or basic file checks fail.
        DataProviderError: The provider request fails.
        OSError: Reading, writing the temporary file, or moving it to its final path fails.

    Errors from file-format readers also pass back to the caller. Call retrieve_raw_file() to
    turn ordinary errors into FailedFile results.
    """
    if offline:
        raise ValueError("Raw file is missing in offline mode")

    with stage_file(destination.parent) as temporary_path:
        if isinstance(request, CensusFileRequest):
            download_census_table(request, temporary_path, raw_data_directory, directories)

        elif isinstance(request, (NhgisTableFileRequest, NhgisBoundaryFileRequest)):
            pending_extract = retrieve_nhgis_extract(
                request, temporary_path, raw_data_directory / directories.saved_nhgis_requests
            )

            if pending_extract is not None:
                return PendingFile(request.destination_relative_path, pending_extract)

        else:
            download_file(
                request.url, temporary_path, download_label=request.destination_relative_path
            )

        check_raw_file(temporary_path, request.file_format)
        temporary_path.replace(destination)

    return ReadyFile(request.destination_relative_path)
