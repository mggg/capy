import os
import pytest
import zipfile

from pipeline.download_geographies import (
    LEVELS,
    OUTPUT_DIR,
    census_output_exists,
    download,
    download_to_file,
    IncompleteDownloadError,
    existing_nhgis_zip,
    fetch_census,
    matches_level,
    select_shapefile_names,
    zip_is_readable,
)


def test_matches_tract_family_levels_and_names():
    config = LEVELS["tracts"]

    assert matches_level(
        {"geographicLevel": "Block Numbering Area", "name": "US_bna_1990"},
        config,
    )
    assert not matches_level(
        {"geographicLevel": "County-Tract", "name": "US_tractcounty_1990"},
        config,
    )


def test_selects_original_1990_tract_family_shapefiles():
    matches = [
        {
            "name": "US_tract_1990_conflated",
            "geographicLevel": "Census Tract",
            "extent": "United States",
            "basis": "2008 TIGER/Line +",
            "sequence": 4,
        },
        {
            "name": "US_tract_1990",
            "geographicLevel": "Census Tract",
            "extent": "United States",
            "basis": "1990 TIGER/Line +",
            "sequence": 1,
        },
        {
            "name": "US_bna_1990",
            "geographicLevel": "Block Numbering Area",
            "extent": "United States",
            "basis": "1990 TIGER/Line +",
            "sequence": 2,
        },
        {
            "name": "US_tractcounty_1990",
            "geographicLevel": "County-Tract",
            "extent": "United States",
            "basis": "1990 TIGER/Line +",
            "sequence": 3,
        },
    ]

    assert select_shapefile_names(matches, 1990, "tracts") == [
        "US_tract_1990",
        "US_bna_1990",
    ]


def test_select_shapefiles_rejects_only_conflated_1990_tracts():
    matches = [
        {
            "name": "US_tract_1990_conflated",
            "geographicLevel": "Census Tract",
            "extent": "United States",
            "basis": "2008 TIGER/Line +",
            "sequence": 1,
        }
    ]

    with pytest.raises(ValueError, match="only conflated tract shapefiles"):
        select_shapefile_names(matches, 1990, "tracts")


def write_zip(path, filename="file.txt", contents="ok"):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(filename, contents)


class FakeResponse:
    def __init__(self, chunks, content_length=None):
        self.chunks = chunks
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        return iter(self.chunks)


def test_zip_is_readable_rejects_partial_zip(tmp_path):
    zip_path = tmp_path / "partial.zip"
    zip_path.write_bytes(b"not a complete zip")

    assert not zip_is_readable(zip_path)


def test_download_replaces_existing_zip(tmp_path, monkeypatch):
    zip_path = tmp_path / "tl_2010_04_bg00.zip"
    write_zip(zip_path, contents="old")

    def fake_download_to_file(url, destination):
        write_zip(destination, contents="new")
        return destination.stat().st_size

    monkeypatch.setattr(
        "pipeline.download_geographies.download_to_file",
        fake_download_to_file,
    )

    assert download("https://example.test/geography.zip", zip_path) == zip_path
    assert zip_is_readable(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        assert zf.read("file.txt") == b"new"


def test_download_retries_partial_result(tmp_path, monkeypatch):
    zip_path = tmp_path / "tl_2010_04_bg00.zip"
    calls = []

    def fake_download_to_file(url, destination):
        calls.append(url)
        if len(calls) == 1:
            destination.write_bytes(b"partial")
            return destination.stat().st_size
        else:
            write_zip(destination)
            return destination.stat().st_size

    monkeypatch.setattr(
        "pipeline.download_geographies.download_to_file",
        fake_download_to_file,
    )
    monkeypatch.setattr("pipeline.download_geographies.time.sleep", lambda seconds: None)

    download("https://example.test/geography.zip", zip_path)

    assert len(calls) == 2
    assert zip_is_readable(zip_path)


def test_download_to_file_rejects_short_response(tmp_path, monkeypatch):
    def fake_get(*args, **kwargs):
        return FakeResponse([b"short"], content_length=100)

    monkeypatch.setattr("pipeline.download_geographies.requests.get", fake_get)

    with pytest.raises(IncompleteDownloadError, match="retrieval incomplete"):
        download_to_file("https://example.test/geography.zip", tmp_path / "out.zip")


def test_census_output_exists_checks_extracted_shapefile(tmp_path):
    url = "https://example.test/tl_2010_29_bg00.zip"

    assert not census_output_exists(url, tmp_path)

    (tmp_path / "tl_2010_29_bg00.shp").touch()

    assert census_output_exists(url, tmp_path)


def test_existing_nhgis_zip_returns_latest_zip(tmp_path):
    older = tmp_path / "nhgis_extract_1.zip"
    newer = tmp_path / "nhgis_extract_2.zip"
    older.touch()
    newer.touch()
    os.utime(older, (1, 1))
    os.utime(newer, (2, 2))

    assert existing_nhgis_zip(tmp_path) == newer


def test_fetch_census_skips_existing_state_outputs(tmp_path, monkeypatch):
    output_path = tmp_path / "census_2000_block_groups"
    output_path.mkdir()
    (output_path / "tl_2010_01_bg00.shp").touch()
    downloaded = []

    def fake_download(url, zip_path):
        downloaded.append(url)
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        write_zip(zip_path)
        return zip_path

    def fake_extract_zip(zip_path, destination):
        (destination / f"{zip_path.stem}.shp").touch()

    monkeypatch.setattr("pipeline.download_geographies.STATE_FIPS", ["01", "02"])
    monkeypatch.setattr("pipeline.download_geographies.download", fake_download)
    monkeypatch.setattr("pipeline.download_geographies.extract_zip", fake_extract_zip)

    assert fetch_census(2000, "block_groups", tmp_path) == output_path

    assert downloaded == [
        "https://www2.census.gov/geo/tiger/TIGER2010/BG/2000/"
        "tl_2010_02_bg00.zip"
    ]
    assert (output_path / "tl_2010_02_bg00.shp").exists()


def test_geography_nhgis_extracts_live_under_geographies_raw_dir():
    assert str(OUTPUT_DIR / "ipums_geography_extracts" / "1990" / "block_groups") == (
        "census_raw/geographies/ipums_geography_extracts/1990/block_groups"
    )
