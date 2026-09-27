"""Choose deterministic shortest polygon connections between geographic graph components."""

from enum import StrEnum

import geopandas as gpd
import networkx as nx
from gerrychain import Graph
from shapely import STRtree


class GraphEdgeAttribute(StrEnum):
    """Distinguish geographic adjacency from added connections and record their lengths."""

    ARTIFICIAL = "artificial"
    CONNECTION_DISTANCE = "connection_distance_m"
    SHARED_PERIMETER = "shared_perim"


def connect_graph_components(graph: Graph, units_df: gpd.GeoDataFrame) -> Graph:
    """Return a copy joined by a minimum-distance spanning tree of the original components.

    Prim's algorithm repeatedly adds the shortest edge leaving the connected component group. Each
    candidate joins the nearest polygons, using their full shapes rather than centroids. Equal
    distances are resolved by the sorted pair of geographic IDs. Original edges retain their
    attributes; added edges have artificial=True and shared_perim=0.

    Note:
        Other MST algorithms could be used, but Prim's is simple and maps well to the problem of
        connecting a small number of disconnected components.

    Args:
        graph (Graph): Geographic adjacency with string geographic node IDs.
        units_df (gpd.GeoDataFrame): Retained polygons indexed by those IDs, in a metre CRS.

    Returns:
        Graph: Connected copy with k-1 new edges for k original components. Empty and single-node
            graphs are unchanged copies. The input graph and polygons are not modified.
    """
    connected_graph = Graph(graph)
    components = sorted(sorted(component) for component in nx.connected_components(graph))

    if len(components) < 2:
        return connected_graph

    component_geometries = [units_df.loc[node_ids].geometry for node_ids in components]
    component_trees = [STRtree(geometries.to_numpy()) for geometries in component_geometries]
    unconnected_components = set(range(1, len(components)))
    best_connections: dict[int, tuple[float, str, str]] = {}
    newest_component = 0

    # Only the best edge to each remaining component is retained, not a complete distance matrix.
    while unconnected_components:
        for component_index in sorted(unconnected_components):
            candidate = find_nearest_polygon_connection(
                component_geometries[newest_component],
                component_geometries[component_index],
                component_trees[component_index],
            )

            if (
                component_index not in best_connections
                or candidate < best_connections[component_index]
            ):
                best_connections[component_index] = candidate

        newest_component = min(unconnected_components, key=best_connections.__getitem__)
        distance, first_id, second_id = best_connections.pop(newest_component)
        connected_graph.add_edge(
            first_id,
            second_id,
            **{
                GraphEdgeAttribute.ARTIFICIAL: True,
                GraphEdgeAttribute.CONNECTION_DISTANCE: distance,
                GraphEdgeAttribute.SHARED_PERIMETER: 0.0,
            },
        )
        unconnected_components.remove(newest_component)

    return connected_graph


def find_nearest_polygon_connection(
    first_geometries: gpd.GeoSeries,
    second_geometries: gpd.GeoSeries,
    second_tree: STRtree,
) -> tuple[float, str, str]:
    """Find the shortest polygon pair, breaking equal-distance ties by geographic IDs.

    Args:
        first_geometries (gpd.GeoSeries): One component's metre-projected polygons, indexed by ID.
        second_geometries (gpd.GeoSeries): Another component's polygons, indexed by ID.
        second_tree (STRtree): Spatial index built from second_geometries in its current order.

    Returns:
        tuple[float, str, str]: Distance in metres and the two IDs in ascending order.
    """
    positions, distances = second_tree.query_nearest(
        first_geometries.to_numpy(), all_matches=True, return_distance=True
    )
    minimum_distance = float(distances.min())
    tied_positions = positions[:, distances == minimum_distance]
    candidate_pairs = []

    for first_position, second_position in tied_positions.T:
        first_id = first_geometries.index[first_position]
        second_id = second_geometries.index[second_position]
        candidate_pairs.append(tuple(sorted((first_id, second_id))))

    first_id, second_id = min(candidate_pairs)

    return minimum_distance, first_id, second_id
