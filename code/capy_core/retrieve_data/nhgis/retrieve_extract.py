"""Ask NHGIS to prepare data, remember the request, and download it when ready.

NHGIS extract requests, status responses, and download links:
https://developer.ipums.org/docs/v2/apiprogram/apis/nhgis/
"""

import json
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ipumspy import IpumsApiClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_serializer

from capy_core.stage_files import StagedFile, stage_file

from ..http_transport import DataProviderError, download_file
from ..raw_file_requests import NhgisBoundaryFileRequest, NhgisTableFileRequest
from .extract_definition import (
    NhgisExtractDefinition,
    NhgisExtractResponse,
    build_nhgis_definition,
    validate_nhgis_definition,
)


@dataclass(frozen=True)
class PendingNhgisExtract:
    """An NHGIS request that is still being prepared and has no downloaded file yet.

    Attributes:
        extract_id (int): Positive account-specific extract number to check on a retry.
        status (Literal["queued", "started", "processing", "submitted"]): Status reported on this
            attempt. A retry uses the saved extract number to check the same request again.
    """

    extract_id: int
    status: Literal["queued", "started", "processing", "submitted"]


def retrieve_nhgis_extract(
    request: NhgisTableFileRequest | NhgisBoundaryFileRequest,
    destination: StagedFile,
    submission_directory: Path,
) -> PendingNhgisExtract | None:
    """Submit or find an NHGIS request, check its status once, and download it if ready.

    NHGIS prepares requested data as an extract. A new request saves its extract number and
    selections; later runs reuse that record instead of submitting again. This function checks the
    extract's status once. If it is completed, it downloads the file immediately, even on the
    first run. If it is still queued or processing, it returns a pending result so the caller can
    continue with other files. NHGIS continues preparing the extract independently. The batch
    runner retries pending files after the initial downloads, up to the configured wait limit.
    This function itself does not repeatedly check or wait for completion.

    Reads IPUMS_API_KEY from the environment and saves one submission record per destination.
    Before downloading, it requires NHGIS's completed selections to match the request and rejects
    reported warnings. Temporary download addresses are not saved in the record. The caller checks
    the downloaded file's format and moves it to its final filename.

    Args:
        request (NhgisTableFileRequest | NhgisBoundaryFileRequest): Table or boundary selection
            and destination used to find its saved submission.
        destination (StagedFile): Empty temporary file to receive a completed download.
        submission_directory (Path): Directory containing saved extract definitions and IDs.

    Returns:
        PendingNhgisExtract | None: Status to check on a retry, or None after downloading the
            completed extract into the temporary file. A pending result leaves that file empty.

    Raises:
        DataProviderError: Credentials are missing, an NHGIS operation fails, or the completed
            extract is invalid. Provider messages that could contain credentials are omitted.
        ValueError: A saved submission record is invalid; the message identifies its path.
        OSError: Reading or saving a local file fails; the filesystem error is preserved.
    """
    api_key = os.environ.get("IPUMS_API_KEY")
    if not api_key:
        raise DataProviderError("Set IPUMS_API_KEY to download NHGIS extracts")

    submission_path = submission_directory / f"{request.destination_relative_path}.json"

    definition = build_nhgis_definition(request)
    client = IpumsApiClient(api_key)
    submitted = submit_or_resume_extract(client, definition, submission_path)

    try:
        status = client.extract_status(submitted.extract_id, "nhgis")
    except Exception as error:  # noqa: BLE001 - SDK errors may contain credentials
        raise DataProviderError(
            f"Could not check NHGIS extract {submitted.extract_id} ({type(error).__name__})"
        ) from None

    if status in ("queued", "started", "processing", "submitted"):
        return PendingNhgisExtract(extract_id=submitted.extract_id, status=status)
    if status != "completed":
        raise DataProviderError(f"NHGIS extract {submitted.extract_id} did not complete")

    try:
        # The SDK warns for warnings: []; inspect the list without printing provider text.
        with warnings.catch_warnings(record=True):
            response = client.get_extract_info(submitted.extract_id, "nhgis")
    except Exception as error:  # noqa: BLE001 - SDK errors may contain signed URLs or keys
        raise DataProviderError(
            f"Could not read NHGIS extract {submitted.extract_id} ({type(error).__name__})"
        ) from None

    try:
        extract_response = NhgisExtractResponse.model_validate(response)
    except ValidationError:
        raise DataProviderError(
            f"NHGIS extract {submitted.extract_id} has invalid metadata"
        ) from None

    if response.get("warnings"):
        raise DataProviderError("NHGIS modified the requested extract; review its definition")

    validate_nhgis_definition(extract_response.request_definition, definition)
    download_kind = "tableData" if isinstance(request, NhgisTableFileRequest) else "gisData"

    if download_kind not in extract_response.download_links:
        raise DataProviderError(
            f"NHGIS extract {submitted.extract_id} has no {download_kind} download"
        )

    download_file(
        extract_response.download_links[download_kind].url,
        destination,
        authorization=api_key,
        download_label=request.destination_relative_path,
    )


class NhgisSubmissionRecord(BaseModel):
    """An extract number and original selections saved so a later run can reuse the request.

    Attributes:
        extract_id (int): Positive account-specific extract number returned by NHGIS.
        request (NhgisExtractDefinition): Original selections, kept whether the extract is
            unfinished, completed, or failed.

    The saved request uses the provider field names sent when submitting the extract.
    Neither credentials nor temporary download URLs belong in this record.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    extract_id: int = Field(gt=0, strict=True)
    request: NhgisExtractDefinition

    @field_serializer("request")
    def serialize_saved_request(self, request: NhgisExtractDefinition) -> dict[str, object]:
        """Use NHGIS's field names when saving, leaving unsupplied optional settings absent."""
        return request.to_provider_request()


def submit_or_resume_extract(
    client: IpumsApiClient, request: NhgisExtractDefinition, submission_path: Path
) -> NhgisSubmissionRecord:
    """Reuse a saved request with the same selections, or submit a new one and save its number.

    The caller must prevent simultaneous changes to this record. A saved request with different
    selections is an error; it is not silently replaced. If submission succeeds but saving fails,
    the account may contain an unrecorded extract; its history must be checked before retrying to
    avoid submitting duplicate work.

    Args:
        client (IpumsApiClient): Authenticated NHGIS client used to submit the request.
        request (NhgisExtractDefinition): Exact selections to submit or find in the saved record.
        submission_path (Path): Record to read, or create after a successful submission.

    Returns:
        NhgisSubmissionRecord: Extract number and original selections. This function does not
            check whether NHGIS has finished preparing the data.

    Raises:
        DataProviderError: A saved submission contains a different request, submission fails, or
            NHGIS returns an invalid extract number.
        ValueError: A saved record is invalid; the message identifies its path.
        OSError: Reading or saving the submission fails.

    Submission errors become DataProviderError messages without provider response text. Local file
    errors retain their filenames so the caller can report which record could not be read or saved.
    """
    if submission_path.exists():
        return load_matching_nhgis_submission(submission_path, request)

    provider_request = request.to_provider_request()
    try:
        extract = client.submit_extract(provider_request)
    except Exception as error:  # noqa: BLE001 - SDK errors may contain credentials
        raise DataProviderError(
            f"Could not submit NHGIS request ({type(error).__name__})"
        ) from None

    try:
        submitted = NhgisSubmissionRecord(extract_id=extract.extract_id, request=request)
    except ValidationError:
        raise DataProviderError("NHGIS returned an invalid extract number") from None

    save_nhgis_submission(submission_path, submitted)

    return submitted


def load_matching_nhgis_submission(
    submission_path: Path, request: NhgisExtractDefinition
) -> NhgisSubmissionRecord:
    """Read a saved extract number and require its original request to match this run.

    Used before local archive reuse and when resuming a download. This checks the saved request,
    not the archive contents, and never contacts NHGIS or changes the submission record.

    Args:
        submission_path (Path): Existing JSON record saved when the extract was submitted.
        request (NhgisExtractDefinition): Definition required by the current file request.

    Returns:
        NhgisSubmissionRecord: Matching request and extract number.

    Raises:
        ValueError: The saved record is invalid; its path is included without its contents.
        DataProviderError: The saved request differs; the message identifies the record to
            replace.
        OSError: Reading the record fails.
    """
    content = submission_path.read_text()
    try:
        submitted = NhgisSubmissionRecord.model_validate_json(content)
    except ValidationError:
        raise ValueError(f"Invalid saved NHGIS request: {submission_path}") from None

    if submitted.request != request:
        raise DataProviderError(
            f"Saved NHGIS submission has a different request: {submission_path}. "
            "For changed selections, use a new raw_data_directory or remove both the old archive "
            "and this submission record before rerunning."
        )

    return submitted


def save_nhgis_submission(path: Path, submission: NhgisSubmissionRecord) -> None:
    """Save the extract number and selections so later runs can check the same NHGIS request.

    The record is written under a temporary name, then moved to the final path in one operation.
    This prevents a partially written record from being mistaken for a completed one.

    Args:
        path (Path): Record path for the requested file; missing directories are created.
        submission (NhgisSubmissionRecord): Extract number and original request. Contains neither
            credentials nor temporary download URLs.

    Raises:
        OSError: Writing the temporary record or moving it to its final path fails. If replacement
            fails, any previous record remains unchanged.
    """
    record = submission.model_dump(mode="json", by_alias=True)
    content = (json.dumps(record, indent=2, allow_nan=False) + "\n").encode("utf-8")

    with stage_file(path.parent) as staged:
        staged.write_chunks((content,))
        staged.publish(path)
