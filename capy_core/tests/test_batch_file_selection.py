import csv
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import gerrychain
import networkx as nx
import pytest
import typer
from shapely.geometry import box

from capy_core import graphs, metrics


@pytest.mark.parametrize("years", ["2010", None])
def test_graph_batch_skips_malformed_names_and_uses_basename_year(
    tmp_path, monkeypatch, capsys, years
):
    input_dir = tmp_path / "inputs"
    geography_gdf = gpd.GeoDataFrame(
        {"GISJOIN": ["A", "B"], "WHITE": [10, 20], "BLACK": [20, 10]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="ESRI:102003",
    )
    for year, parent_year in [(2010, 2020), (2020, 2010)]:
        directory = input_dir / str(parent_year)
        directory.mkdir(parents=True)
        geography_gdf.to_file(
            directory / f"tracts_in_county_01001_{year}_example_vintage.gpkg", driver="GPKG"
        )
    malformed_path = input_dir / "2020" / "unrelated.gpkg"
    malformed_path.write_text("not a GeoPackage")
    monkeypatch.setattr(graphs, "ProcessPoolExecutor", ThreadPoolExecutor)
    output_dir = tmp_path / "graphs"

    graphs.main(str(input_dir / "*" / "*.gpkg"), str(output_dir), workers=1, years=years)

    expected_years = ["2010"] if years else ["2010", "2020"]
    assert (
        sorted(path.parent.name for path in output_dir.glob("*/*_connected.json")) == expected_years
    )
    for path in output_dir.glob("*/*_connected.json"):
        graph = gerrychain.Graph.from_json(str(path))
        assert len(graph) == 2
        assert nx.is_connected(graph)
    assert str(malformed_path) in capsys.readouterr().err


@pytest.mark.parametrize("years", ["2010", None])
def test_metric_batch_records_bad_names_and_finishes_valid_files(
    tmp_path, monkeypatch, capsys, years
):
    input_dir = tmp_path / "inputs"
    graph = gerrychain.Graph(nx.path_graph(4))
    for node in graph:
        graph.nodes[node].update(
            WHITE=10 * (node + 1),
            BLACK=40 - 10 * node,
            POC=40 - 10 * node,
            TOTPOP=50,
            centroid_x=float(node),
            centroid_y=0.0,
        )
    valid_paths = []
    for year, parent_year in [(2010, 2020), (2020, 2010)]:
        directory = input_dir / str(parent_year)
        directory.mkdir(parents=True)
        path = directory / f"tracts_in_county_01001_{year}_example_vintage_connected.json"
        graph.to_json(str(path))
        valid_paths.append(path)
    malformed_path = input_dir / "2020" / "unrelated.json"
    malformed_path.write_text("not JSON")
    failures_path = tmp_path / "failures.csv"
    monkeypatch.setenv("METRIC_FAILURES_FILE", str(failures_path))
    monkeypatch.setattr(metrics, "ProcessPoolExecutor", ThreadPoolExecutor)
    output_path = tmp_path / "results" / "metrics.csv"

    with pytest.raises(typer.Exit) as error:
        metrics.main(
            str(input_dir / "*" / "*.json"),
            "WHITE",
            "BLACK",
            "TOTPOP",
            output_path,
            workers=1,
            years=years,
        )

    assert error.value.exit_code == 1
    expected_paths = valid_paths[:1] if years else valid_paths
    with output_path.open() as source:
        rows = list(csv.DictReader(source))
    assert {row["filename"] for row in rows} == {str(path) for path in expected_paths}
    assert all(int(row["total_nodes"]) == 4 for row in rows)
    with failures_path.open() as source:
        failures = list(csv.DictReader(source))
    assert len(failures) == 1
    assert failures[0]["filename"] == str(malformed_path)
    assert failures[0]["study_area_code"] == ""
    assert failures[0]["error_message"]
    assert str(malformed_path) in capsys.readouterr().err
