import geopandas as gpd
import networkx as nx
from shapely.geometry import Point

from pipeline.build.gen_duals import connect_components


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

    connected = connect_components(shp, graph)

    assert nx.is_connected(connected)
    assert connected.has_edge("B", "C")
