import csv

import geopandas as gpd
from shapely.geometry import box

from capy_core.graphs import _process_file
from capy_core.metrics import write_failure
from capy_core.preprocessing.overlap_quality import (
    _collect_clipped_records,
    _collect_definitions,
)
from capy_core.preprocessing.overlaps import _run_year
from capy_core.preprocessing.study_areas import build_county_definitions


def test_definition_selection_graph_and_report_share_geography_identity(tmp_path):
    definitions_dir = tmp_path / "definitions"
    county_file = tmp_path / "2020_counties.gpkg"
    counties = gpd.GeoDataFrame(
        {"STATEFP": ["01"], "COUNTYFP": ["001"], "TOTPOP": [100]},
        geometry=[box(0, 0, 2, 1)],
        crs="ESRI:102003",
    )
    counties.to_file(county_file, driver="GPKG")
    build_county_definitions(str(county_file), str(definitions_dir), "region_in_1990")

    census_dir = tmp_path / "census"
    (census_dir / "tracts").mkdir(parents=True)
    tracts = gpd.GeoDataFrame(
        {
            "STATEFP": ["01", "01"],
            "GISJOIN": ["A", "B"],
            "WHITE": [25, 25],
            "BLACK": [25, 25],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="ESRI:102003",
    )
    tracts.to_file(census_dir / "tracts/2010_tracts_01.gpkg", driver="GPKG")
    selected_dir = tmp_path / "selected_in_folder"

    _run_year(
        str(definitions_dir / "*.gpkg"),
        str(selected_dir),
        "tracts",
        "2010",
        "region_in_1990",
        str(census_dir),
    )
    stem = "tracts_in_county_01001_2010_region_in_1990_vintage"
    selected_file = selected_dir / f"{stem}.gpkg"
    assert selected_file.is_file()

    graph_dir = tmp_path / "graphs"
    year, dropped = _process_file(str(selected_file), str(graph_dir))
    assert year == "2010"
    assert dropped is None
    assert (graph_dir / "2010" / f"{stem}_orig.json").is_file()
    assert (graph_dir / "2010" / f"{stem}_connected.json").is_file()

    (definitions_dir / "unrelated.gpkg").touch()
    (selected_dir / "unrelated.gpkg").touch()
    definitions = _collect_definitions(definitions_dir)
    selected = _collect_clipped_records(selected_dir, "tracts", "county")
    assert definitions[["sa_type", "sa_id", "vintage"]].values.tolist() == [
        ["county", "01001", "region_in_1990"]
    ]
    assert selected[
        ["sa_type", "sa_id", "vintage", "year", "unit_count"]
    ].values.tolist() == [["county", "01001", "region_in_1990", "2010", 2]]


def test_metric_failure_records_code_without_losing_malformed_filename_errors(
    tmp_path, monkeypatch
):
    failures = tmp_path / "failures.csv"
    monkeypatch.setenv("METRIC_FAILURES_FILE", str(failures))
    for filename in (
        "parent_in_name/tracts_in_county_01001_2010_region_in_1990_vintage_connected.json",
        "malformed.json",
    ):
        write_failure(
            filename, "BLACK", "WHITE", "TOTPOP", ValueError("missing population")
        )

    with failures.open() as source:
        rows = list(csv.DictReader(source))
    assert [row["study_area_code"] for row in rows] == ["01001", ""]
    assert [row["error_message"] for row in rows] == [
        "missing population",
        "missing population",
    ]
