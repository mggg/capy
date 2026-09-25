"""NHGIS submission, resumption, completed-definition checks, and archive retrieval."""

import io
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from capy_core.pipeline_config import RawDataSubdirectories
from capy_core.retrieve_data.http_transport import DataProviderError
from capy_core.retrieve_data.nhgis.extract_definition import (
    NhgisDatasetSelection,
    NhgisExtractDefinition,
    build_nhgis_definition,
    validate_nhgis_definition,
)
from capy_core.retrieve_data.nhgis.retrieve_extract import (
    NhgisSubmissionRecord,
    submit_or_resume_extract,
)
from capy_core.retrieve_data.raw_file_requests import (
    NhgisBoundaryFileRequest,
    NhgisTableFileRequest,
)
from capy_core.retrieve_data.retrieve_raw_file import (
    FailedFile,
    PendingFile,
    ReadyFile,
    retrieve_raw_file,
)


class ArchiveResponse:
    """A successful HTTP response carrying the archive bytes supplied by a test."""

    status_code = 200

    def __init__(self, content):
        self.content = content
        self.headers = {"Content-Length": str(len(content))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, size):
        yield self.content


def make_zip(members):
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return content.getvalue()


@pytest.mark.parametrize("provider_warning", [False, True])
def test_completed_nhgis_extract_checks_provider_warnings(tmp_path, monkeypatch, provider_warning):
    from ipumspy import IpumsApiClient

    content = make_zip({"population.csv": b"GISJOIN,YEAR\nG0100010,1980\n"})

    class Client(IpumsApiClient):
        def __init__(self, key):
            assert key == "private-nhgis-key"
            super().__init__(key)

        def submit_extract(self, request):
            return SimpleNamespace(extract_id=17)

        def extract_status(self, number, collection):
            return "completed"

        def get(self, url, params):
            response = {
                "warnings": ["modified request"] if provider_warning else [],
                "downloadLinks": {"tableData": {"url": "https://example.org/signed?token=private"}},
                "extractDefinition": {
                    "collection": "nhgis",
                    "datasets": {"1980_STF1": {"dataTables": ["NT7"], "geogLevels": ["county"]}},
                    "dataFormat": "csv_header",
                    "breakdownAndDataTypeLayout": "single_file",
                },
            }
            return SimpleNamespace(json=lambda: response)

    monkeypatch.setenv("IPUMS_API_KEY", "private-nhgis-key")
    monkeypatch.setattr("capy_core.retrieve_data.nhgis.retrieve_extract.IpumsApiClient", Client)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: ArchiveResponse(content))
    file_request = NhgisTableFileRequest(
        destination_relative_path="nhgis/population.zip",
        dataset_name="1980_STF1",
        tables=("NT7",),
        geographic_levels=("county",),
    )
    raw = tmp_path / "raw"
    result = retrieve_raw_file(file_request, raw, False, directories=RawDataSubdirectories())
    if provider_warning:
        assert isinstance(result, FailedFile) and "modified" in result.error_message
        assert not (raw / file_request.destination_relative_path).exists()
        return
    assert isinstance(result, ReadyFile)
    submission_records = list((raw / "saved_nhgis_requests").rglob("*.json"))
    assert len(submission_records) == 1
    for path in submission_records:
        record = path.read_text()
        assert "private-nhgis-key" not in record and "token=private" not in record


def test_nhgis_changed_table_selections_are_rejected():
    requested = NhgisExtractDefinition.model_validate(
        {
            "collection": "nhgis",
            "datasets": {"1980_STF1": {"dataTables": ["NT7", "NT9B"], "geogLevels": ["county"]}},
        }
    )
    modified = NhgisExtractDefinition.model_validate(
        {
            "collection": "nhgis",
            "datasets": {"1980_STF1": {"dataTables": ["NT9B"], "geogLevels": ["county"]}},
        }
    )
    with pytest.raises(DataProviderError, match="tables"):
        validate_nhgis_definition(modified, requested)
    validate_nhgis_definition(requested, requested)


@pytest.mark.parametrize(
    "dataset,breakdowns,returned_breakdowns,expected_error",
    [
        ("1980_STF1", ("bs03.ge0000", "bs03.ge0100"), ("bs03.ge0000", "bs03.ge0100"), "layout"),
        ("unknown_dataset", (), (), "layout"),
        ("1980_STF1", (), ("bs03.ge0100",), "breakdowns"),
    ],
)
def test_missing_layout_does_not_hide_meaningful_selection_changes(
    dataset, breakdowns, returned_breakdowns, expected_error
):
    requested = NhgisExtractDefinition(
        datasets={dataset: NhgisDatasetSelection(tables=("NT7",), breakdowns=breakdowns)},
        data_layout="single_file",
    )
    actual = NhgisExtractDefinition(
        datasets={dataset: NhgisDatasetSelection(tables=("NT7",), breakdowns=returned_breakdowns)},
    )

    with pytest.raises(DataProviderError, match=expected_error):
        validate_nhgis_definition(actual, requested)


@pytest.mark.parametrize(
    "dataset,year,tables,whole_area,urban_area",
    [
        ("1980_STF1", "1980", ("NT1A", "NT7"), "bs03.ge0000", "bs03.ge0100"),
        ("1990_STF1", "1990", ("NP1", "NP10"), "bs09.ge00", "bs09.ge01"),
    ],
)
def test_nhgis_defaults_and_omitted_layout_preserve_population_selection(
    dataset, year, tables, whole_area, urban_area
):
    request = NhgisTableFileRequest(
        destination_relative_path="population.zip",
        dataset_name=dataset,
        tables=tables,
        geographic_levels=("county",),
    )
    requested = build_nhgis_definition(request)
    returned = requested.to_provider_request()
    returned.pop("breakdownAndDataTypeLayout")
    returned["version"] = 2
    returned["timeSeriesTableLayout"] = "time_by_column_layout"
    selection = returned["datasets"][dataset]
    selection["dataTables"] = list(reversed(tables))
    selection["years"] = [year]
    selection["breakdownValues"] = [whole_area]

    validate_nhgis_definition(NhgisExtractDefinition.model_validate(returned), requested)

    selection["breakdownValues"] = [urban_area]
    with pytest.raises(DataProviderError, match="breakdowns"):
        validate_nhgis_definition(NhgisExtractDefinition.model_validate(returned), requested)


def test_nhgis_submission_roundtrip_and_corrupt_resume(tmp_path):
    requests = []

    class Client:
        def submit_extract(self, request):
            requests.append(request)
            return SimpleNamespace(extract_id=12)

    request = NhgisExtractDefinition(datasets={"1980_STF1": NhgisDatasetSelection(tables=("NT7",))})
    path = tmp_path / "request.json"
    submitted = submit_or_resume_extract(Client(), request, path)
    assert requests[0]["collection"] == "nhgis"
    assert NhgisSubmissionRecord.model_validate_json(path.read_text()) == submitted
    assert submit_or_resume_extract(Client(), request, path) == submitted
    assert len(requests) == 1

    changed_request = NhgisExtractDefinition(
        datasets={"1980_STF1": NhgisDatasetSelection(tables=("NT1A",))}
    )
    with pytest.raises(DataProviderError, match="different request"):
        submit_or_resume_extract(Client(), changed_request, path)

    saved = json.loads(path.read_text())
    assert saved["request"] == request.to_provider_request()
    saved["extract_id"] = "private-api-key"
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="Invalid saved NHGIS request") as failure:
        submit_or_resume_extract(Client(), request, path)
    assert str(path) in str(failure.value)
    assert "private-api-key" not in str(failure.value)
    assert len(requests) == 1


@pytest.mark.parametrize("failed_operation", ["submit", "status", "metadata"])
def test_nhgis_provider_failures_identify_operation_without_exposing_credentials(
    tmp_path, monkeypatch, failed_operation
):
    class Client:
        def __init__(self, key):
            pass

        def submit_extract(self, definition):
            if failed_operation == "submit":
                raise RuntimeError("private-api-key")
            return SimpleNamespace(extract_id=42)

        def extract_status(self, number, collection):
            if failed_operation == "status":
                raise RuntimeError("private-api-key")
            return "completed"

        def get_extract_info(self, number, collection):
            raise RuntimeError("https://example.org/?token=private-api-key")

    monkeypatch.setenv("IPUMS_API_KEY", "private-api-key")
    monkeypatch.setattr("capy_core.retrieve_data.nhgis.retrieve_extract.IpumsApiClient", Client)
    request = NhgisBoundaryFileRequest(
        destination_relative_path="nhgis/counties.zip",
        shapefiles=("us_county_1980_tl2008",),
    )
    result = retrieve_raw_file(request, tmp_path, False, RawDataSubdirectories())

    assert isinstance(result, FailedFile)
    expected = {
        "submit": "submit NHGIS request",
        "status": "check NHGIS extract 42",
        "metadata": "read NHGIS extract 42",
    }
    assert expected[failed_operation] in result.error_message
    assert "private-api-key" not in result.error_message
    assert not (tmp_path / request.destination_relative_path).exists()


def test_nhgis_boundary_download_retry_reuses_submission(tmp_path, monkeypatch):
    content = make_zip({"counties.shp": b"example shape bytes"})
    submissions = []

    class Client:
        def __init__(self, key):
            pass

        def submit_extract(self, definition):
            submissions.append(definition)
            return SimpleNamespace(extract_id=23)

        def extract_status(self, number, collection):
            return "completed"

        def get_extract_info(self, number, collection):
            return {
                "extractDefinition": {"shapefiles": ["us_county_1980_tl2008"]},
                "downloadLinks": {"gisData": {"url": "https://example.org/counties.zip"}},
            }

    monkeypatch.setenv("IPUMS_API_KEY", "secret")
    monkeypatch.setattr("capy_core.retrieve_data.nhgis.retrieve_extract.IpumsApiClient", Client)
    get = Mock(side_effect=[requests.ConnectionError("private-key"), ArchiveResponse(content)])
    monkeypatch.setattr("requests.get", get)
    monkeypatch.setattr(
        "capy_core.retrieve_data.retrieve_raw_file.time.sleep", lambda seconds: None
    )
    request = NhgisBoundaryFileRequest(
        destination_relative_path="nhgis/counties.zip",
        shapefiles=("us_county_1980_tl2008",),
    )

    result = retrieve_raw_file(
        request, tmp_path, offline=False, directories=RawDataSubdirectories()
    )

    assert isinstance(result, ReadyFile)
    assert (tmp_path / request.destination_relative_path).read_bytes() == content
    assert submissions == [{"collection": "nhgis", "shapefiles": ["us_county_1980_tl2008"]}]
    assert get.call_count == 2


@pytest.mark.parametrize(
    "block_status,max_wait_minutes,expected_checks,expected_waits,expected_type",
    [
        ("completed", 1, [1, 2, 2], [40], ReadyFile),
        ("queued", 1, [1, 2, 2, 2], [40, 20], PendingFile),
        ("failed", 1, [1, 2, 2], [40], FailedFile),
        ("completed", 0, [1, 2], [], PendingFile),
        ("interrupted", 1, [1, 2, 2], [40], ReadyFile),
    ],
)
def test_pending_block_retries_preserve_completed_tract_and_saved_submissions(
    tmp_path,
    monkeypatch,
    block_status,
    max_wait_minutes,
    expected_checks,
    expected_waits,
    expected_type,
):
    from capy_core.pipeline_config import PipelineConfig
    from capy_core.retrieve_data import retrieve_files as retrieval
    from capy_core.retrieve_data.prepare_file_requests import build_raw_file_requests

    config = PipelineConfig(
        census_geography_levels=("tracts", "blocks"),
        census_geography_years=(1990,),
        max_parallel_downloads=1,
        nhgis_retry_interval_seconds=40,
        nhgis_max_wait_minutes=max_wait_minutes,
        raw_data_subdirectories=RawDataSubdirectories(saved_nhgis_requests="status/extracts"),
    )
    requests = {
        request.destination_relative_path: request for request in build_raw_file_requests(config)
    }
    selected = [requests[f"nhgis/1990/{level}/population.zip"] for level in ("tracts", "blocks")]
    submissions = []
    status_checks = []
    content = make_zip({"population.csv": b"GISJOIN,YEAR\nG0100010,1990\n"})
    elapsed_seconds = 0
    waits = []

    def wait(seconds):
        nonlocal elapsed_seconds
        waits.append(seconds)
        if block_status == "interrupted":
            raise KeyboardInterrupt
        elapsed_seconds += seconds

    class Client:
        def __init__(self, key):
            pass

        def submit_extract(self, definition):
            submissions.append(definition)
            return SimpleNamespace(extract_id=len(submissions))

        def extract_status(self, number, collection):
            status_checks.append(number)
            if number == 1:
                return "completed"
            return "queued" if status_checks.count(2) == 1 else block_status

        def get_extract_info(self, number, collection):
            return {
                "extractDefinition": submissions[number - 1],
                "downloadLinks": {"tableData": {"url": "https://example.org/data?token=private"}},
            }

    monkeypatch.setenv("IPUMS_API_KEY", "test-key")
    monkeypatch.setattr("capy_core.retrieve_data.nhgis.retrieve_extract.IpumsApiClient", Client)
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: ArchiveResponse(content))
    monkeypatch.setattr(retrieval.time, "monotonic", lambda: elapsed_seconds)
    monkeypatch.setattr(retrieval.time, "sleep", wait)

    if block_status == "interrupted":
        with pytest.raises(KeyboardInterrupt):
            retrieval.retrieve_files(config, tmp_path, selected)
        assert not (
            tmp_path / config.raw_data_directory / selected[1].destination_relative_path
        ).exists()
        block_status = "completed"

    outcome = retrieval.retrieve_files(config, tmp_path, selected)
    assert isinstance(outcome.file_results[0], ReadyFile)
    assert isinstance(outcome.file_results[1], expected_type)
    assert outcome.complete == (expected_type is ReadyFile)
    assert len(submissions) == 2
    assert status_checks == expected_checks
    assert waits == expected_waits
    raw_directory = tmp_path / config.raw_data_directory
    for request in selected:
        saved = (
            raw_directory / "status/extracts" / f"{request.destination_relative_path}.json"
        ).read_text()
        assert "test-key" not in saved and "token=private" not in saved

    assert (raw_directory / selected[0].destination_relative_path).read_bytes() == content
    block_path = raw_directory / selected[1].destination_relative_path
    if expected_type is ReadyFile:
        assert block_path.read_bytes() == content
    else:
        assert not block_path.exists()
    assert not list(raw_directory.rglob(".retrieval-*"))


@pytest.mark.parametrize("file_exists", [False, True])
@pytest.mark.parametrize(
    "original,changed",
    [
        (
            NhgisTableFileRequest(
                destination_relative_path="tables.zip",
                dataset_name="1990_STF1",
                tables=("NP1",),
                geographic_levels=("tract",),
            ),
            NhgisTableFileRequest(
                destination_relative_path="tables.zip",
                dataset_name="1990_STF1",
                tables=("NP1", "NP10"),
                geographic_levels=("tract",),
            ),
        ),
        (
            NhgisBoundaryFileRequest(
                destination_relative_path="boundaries.zip", shapefiles=("us_tract_1980_tl2000",)
            ),
            NhgisBoundaryFileRequest(
                destination_relative_path="boundaries.zip", shapefiles=("us_county_1980_tl2008",)
            ),
        ),
    ],
)
def test_changed_nhgis_request_rejects_saved_archive_or_submission(
    tmp_path, original, changed, file_exists
):
    from capy_core.retrieve_data.nhgis.retrieve_extract import save_nhgis_submission

    directories = RawDataSubdirectories(saved_nhgis_requests="status/extracts")
    submission_path = (
        tmp_path / directories.saved_nhgis_requests / f"{original.destination_relative_path}.json"
    )
    save_nhgis_submission(
        submission_path,
        NhgisSubmissionRecord(extract_id=12, request=build_nhgis_definition(original)),
    )
    saved_record = submission_path.read_bytes()
    archive_path = tmp_path / original.destination_relative_path
    content = make_zip({"tracts.shp": b"shape", "population.csv": b"population\n10\n"})
    if file_exists:
        archive_path.write_bytes(content)
        assert isinstance(retrieve_raw_file(original, tmp_path, True, directories), ReadyFile)

    result = retrieve_raw_file(changed, tmp_path, True, directories)

    assert isinstance(result, FailedFile)
    assert result.destination_relative_path == changed.destination_relative_path
    assert "different request" in result.error_message
    assert str(submission_path) in result.error_message
    assert "archive" in result.error_message
    assert submission_path.read_bytes() == saved_record
    if file_exists:
        assert archive_path.read_bytes() == content
        submission_path.unlink()
        assert isinstance(retrieve_raw_file(changed, tmp_path, True, directories), ReadyFile)
    else:
        assert not archive_path.exists()
