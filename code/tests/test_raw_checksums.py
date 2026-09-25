"""Published checksums describe raw bytes without becoming a retrieval requirement."""

import hashlib

import pytest
from capy_core.retrieve_data.raw_file_requests import PublicFileRequest, RawFileFormat
from record_raw_checksums import record_raw_checksums


def test_checksum_reference_records_bytes_and_preserves_previous_output_on_missing_input(tmp_path):
    raw_directory = tmp_path / "raw"
    raw_directory.mkdir()
    payload = b"name,population\nexample,17\n"
    (raw_directory / "population.csv").write_bytes(payload)
    request = PublicFileRequest(
        destination_relative_path="population.csv",
        file_format=RawFileFormat.CSV,
        url="https://example.org/population.csv",
    )
    output_path = tmp_path / "raw_checksums.sha256"
    record_raw_checksums(raw_directory, [request], output_path)
    assert output_path.read_text() == f"{hashlib.sha256(payload).hexdigest()}  population.csv\n"

    (raw_directory / "population.csv").unlink()
    with pytest.raises(FileNotFoundError):
        record_raw_checksums(raw_directory, [request], output_path)
    assert output_path.read_text() == f"{hashlib.sha256(payload).hexdigest()}  population.csv\n"

    with pytest.raises(ValueError, match="outside"):
        record_raw_checksums(raw_directory, [request], raw_directory / "population.csv")
