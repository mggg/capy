import geopandas as gpd
import gerrychain
import networkx as nx
import pytest
from shapely.geometry import Point, box

from capy_core.graphs import _process_file, connect_components


def test_connect_components_adds_nearest_bridge():
    shp = gpd.GeoDataFrame(
        {"GISJOIN": ["A", "B", "C", "D"]},
        geometry=[Point(0, 0), Point(1, 0), Point(10, 0), Point(11, 0)],
        crs="EPSG:3857",
    )
    graph = nx.Graph()
    for node in shp["GISJOIN"]:
        graph.add_node(node, GISJOIN=node)
    graph.add_edge("A", "B")
    graph.add_edge("C", "D")

    connected, n_added = connect_components(shp, graph)

    assert nx.is_connected(connected)
    assert connected.has_edge("B", "C")


@pytest.mark.parametrize("populations", [[1, 0, 1], [0, 0, 0], [1, 0, 0]])
def test_process_file_connects_after_dropping_nodes(tmp_path, populations):
    source = tmp_path / "2020" / "tracts_in_cbsa_12345_2020.gpkg"
    source.parent.mkdir()
    geofile = gpd.GeoDataFrame(
        {"GISJOIN": ["A", "B", "C"], "WHITE": populations, "BLACK": [0, 0, 0]},
        geometry=[box(i, 0, i + 1, 1) for i in range(3)],
        crs="ESRI:102003",
    )
    geofile.to_file(source, driver="GPKG")
    output = tmp_path / "graphs"

    year, dropped = _process_file(str(source), str(output))

    original = gerrychain.Graph.from_json(str(output / year / f"{source.stem}_orig.json"))
    connected = gerrychain.Graph.from_json(str(output / year / f"{source.stem}_connected.json"))
    assert len(original) == 3
    assert nx.is_connected(original)
    assert set(dropped.GISJOIN) == {name for name, pop in zip("ABC", populations) if pop == 0}
    assert {attrs["GISJOIN"] for _, attrs in connected.nodes(data=True)} == {
        name for name, pop in zip("ABC", populations) if pop > 0
    }
    if connected:
        assert nx.is_connected(connected)


def test_process_file_rejects_disconnected_output(tmp_path, monkeypatch):
    source = tmp_path / "2020" / "tracts_in_cbsa_12345_2020.gpkg"
    source.parent.mkdir()
    geofile = gpd.GeoDataFrame(
        {"GISJOIN": ["A", "B", "C"], "WHITE": [1, 0, 1], "BLACK": [0, 0, 0]},
        geometry=[box(i, 0, i + 1, 1) for i in range(3)],
        crs="ESRI:102003",
    )
    geofile.to_file(source, driver="GPKG")
    monkeypatch.setattr("capy_core.graphs.connect_components", lambda geofile, graph, attr: (graph, 0))
    output = tmp_path / "graphs"

    with pytest.raises(ValueError, match="still disconnected"):
        _process_file(str(source), str(output))

    assert not (output / "2020" / f"{source.stem}_connected.json").exists()
