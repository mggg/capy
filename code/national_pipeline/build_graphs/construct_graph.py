"""Filter study-area units, construct geographic adjacency, and account for population losses."""

import ast
import warnings
from enum import StrEnum
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd
from gerrychain import Graph

from national_pipeline.population_table_columns import GeographyColumn, PopulationColumn

from .connect_components import GraphEdgeAttribute, connect_graph_components

# NOTE: Historical NHGIS outlines contain microscopic source slivers; all measured 1990
# CBSA block-group overlaps were below 100 mm². At this scale we suppress warning noise,
# not geometry or connections. Larger overlaps are reported when warnings are enabled.
MAX_SILENT_OVERLAP_AREA_M2 = 0.0001  # 100 mm², measured in the graph's metre CRS.
OVERLAP_WARNING_PREFIX = "Found overlaps among the given polygons. Indices of overlaps: "


class GraphNodeAttribute(StrEnum):
    """Projected polygon centroids used by distance-based spatial statistics."""

    CENTROID_X = "centroid_x"
    CENTROID_Y = "centroid_y"


def build_connected_graph(
    units_df: gpd.GeoDataFrame, *, warn_on_polygon_overlaps: bool = True
) -> tuple[Graph, pd.DataFrame]:
    """Build a rook-adjacency graph, retaining units with positive White-plus-Black population.

    Both White–Black and White–POC analysis use this graph. Units removed by the filter can have
    other residents; their identities and all four population counts are returned separately.
    Geographic edges require a positive-length intersection, including polygon overlaps. Counts
    remain attached to unique Census records; overlapping shapes do not duplicate their counts.
    Added component connections are marked so removing them recovers geographic adjacency.

    Args:
        units_df (gpd.GeoDataFrame): Whole selected polygons with unique string GEOIDs and the four
            study population columns. A defined CRS and valid polygon geometries are required.
        warn_on_polygon_overlaps (bool): Report overlaps above 100 mm²; defaults to True. False
            suppresses GerryChain overlap warnings without changing the graph or other warnings.

    Returns:
        tuple[Graph, pd.DataFrame]: Connected graph and removed-unit counts. The graph records
            input, retained, and removed totals and the initial component count. Nodes retain
            projected centroid coordinates for distance-based statistics. The graph has no nodes
            when no units survive filtering. Inputs are not modified.

    Raises:
        ValueError: Identities, population definitions, or polygons are invalid, or graph counts
            or connections fail their checks. Geometry-library exceptions also propagate.
    """
    check_graph_units(units_df)
    units_df = gpd.GeoDataFrame(
        units_df.to_crs("ESRI:102003")
        .set_index(GeographyColumn.GEOGRAPHIC_ID, drop=False)
        .sort_index(),
        crs="ESRI:102003",
    )
    retained_mask = (
        units_df[PopulationColumn.NON_HISPANIC_WHITE]
        + units_df[PopulationColumn.NON_HISPANIC_BLACK]
    ).gt(0)
    retained_units_df = units_df.loc[retained_mask]
    removed_units_df = pd.DataFrame(
        units_df.loc[~retained_mask, [GeographyColumn.GEOGRAPHIC_ID, *PopulationColumn]]
    ).reset_index(drop=True)

    graph = Graph()

    if not retained_units_df.empty:
        with warnings.catch_warnings(record=True) as graph_warnings:
            # Islands are expected before the explicit component-connection step.
            warnings.filterwarnings("ignore", message="Found islands.*", category=UserWarning)
            warnings.filterwarnings(
                "always" if warn_on_polygon_overlaps else "ignore",
                message=r"Found overlaps among the given polygons\. Indices of overlaps: ",
                category=UserWarning,
                module=r"gerrychain\.graph\.adjacency$",
            )
            graph = Graph.from_geodataframe(
                retained_units_df,
                adjacency="rook",
                cols_to_add=[GeographyColumn.GEOGRAPHIC_ID, *PopulationColumn],
            )

        for graph_warning in graph_warnings:
            report_unexpected_graph_warning(graph_warning, retained_units_df)

    centroids = retained_units_df.geometry.centroid

    for node_id, centroid in centroids.items():
        graph.nodes[node_id][GraphNodeAttribute.CENTROID_X] = float(centroid.x)
        graph.nodes[node_id][GraphNodeAttribute.CENTROID_Y] = float(centroid.y)

    for _, _, edge_attributes in graph.edges(data=True):
        edge_attributes[GraphEdgeAttribute.ARTIFICIAL] = False

    initial_component_count = nx.number_connected_components(graph)
    connected_graph = connect_graph_components(graph, retained_units_df)
    expected_added_edges = max(0, initial_component_count - 1)

    if connected_graph.number_of_edges() != graph.number_of_edges() + expected_added_edges:
        raise ValueError("Component connections did not add exactly k-1 edges")

    if connected_graph and not nx.is_connected(connected_graph):
        raise ValueError("Graph remains disconnected after adding component connections")

    for column in PopulationColumn:
        retained_population = sum(
            connected_graph.nodes[node_id][column] for node_id in connected_graph
        )

        if retained_population + int(removed_units_df[column].sum()) != int(units_df[column].sum()):
            raise ValueError(f"Graph filtering failed to conserve {column}")

    # NOTE: This will add things like the CRS and population counts to the graph's metadata
    # dictionary.
    connected_graph.graph.update(
        crs="ESRI:102003",
        adjacency="rook",
        population_filter="WHITE + BLACK > 0",
        initial_component_count=initial_component_count,
        artificial_edge_count=expected_added_edges,
        input_unit_count=len(units_df),
        removed_unit_count=len(removed_units_df),
        input_population={column: int(units_df[column].sum()) for column in PopulationColumn},
        retained_population={
            column: int(retained_units_df[column].sum()) for column in PopulationColumn
        },
        removed_population={
            column: int(removed_units_df[column].sum()) for column in PopulationColumn
        },
    )

    return connected_graph, removed_units_df


def report_unexpected_graph_warning(
    graph_warning: warnings.WarningMessage, units_df: gpd.GeoDataFrame
) -> None:
    """Keep warnings visible except for polygon overlaps at or below 100 square millimetres.

    GerryChain reports overlapping IDs as a Python set in its warning text. Read that set with
    literal_eval, without executing code, and measure each reported pair. An unknown warning
    format is passed through unchanged. This changes reporting, not polygons or graph edges.

    Args:
        graph_warning (warnings.WarningMessage): Warning captured during geographic adjacency.
        units_df (gpd.GeoDataFrame): Retained polygons indexed by geographic ID, in projected metres.

    Raises:
        Warning: A remaining warning is configured as an error by the caller.
    """
    message = str(graph_warning.message)
    warning_module = Path(graph_warning.filename).stem

    if message.startswith(OVERLAP_WARNING_PREFIX):
        warning_module = "gerrychain.graph.adjacency"
        try:
            overlap_pairs = ast.literal_eval(message.removeprefix(OVERLAP_WARNING_PREFIX))
        except (ValueError, SyntaxError):
            overlap_pairs = None

        if isinstance(overlap_pairs, set) and all(
            isinstance(pair, tuple)
            and len(pair) == 2
            and all(isinstance(geographic_id, str) for geographic_id in pair)
            for pair in overlap_pairs
        ):
            unexpected_pairs = overlap_pairs.copy()

            for first_id, second_id in overlap_pairs:
                if first_id not in units_df.index or second_id not in units_df.index:
                    continue

                overlap_area = (
                    units_df.loc[first_id]
                    .geometry.intersection(units_df.loc[second_id].geometry)
                    .area
                )

                if 0 < overlap_area <= MAX_SILENT_OVERLAP_AREA_M2:
                    unexpected_pairs.remove((first_id, second_id))

            if not unexpected_pairs:
                return

            message = f"{OVERLAP_WARNING_PREFIX}{unexpected_pairs}"

    warnings.warn_explicit(
        message,
        graph_warning.category,
        graph_warning.filename,
        graph_warning.lineno,
        module=warning_module,
    )


def check_graph_units(units_df: gpd.GeoDataFrame) -> None:
    """Reject ambiguous identities, invalid polygons, and invalid study population definitions.

    Args:
        units_df (gpd.GeoDataFrame): Selected units before any filtering or projection.

    Raises:
        ValueError: A required column, identity, population count, or polygon is invalid.
    """
    required_columns = [GeographyColumn.GEOGRAPHIC_ID, *PopulationColumn, "geometry"]

    if any(column not in units_df for column in required_columns):
        raise ValueError("Graph inputs need GEOID, all study population columns, and geometry")

    geographic_ids = units_df[GeographyColumn.GEOGRAPHIC_ID]

    if geographic_ids.duplicated().any() or not bool(
        geographic_ids.map(
            lambda geographic_id: isinstance(geographic_id, str) and bool(geographic_id.strip())
        ).all()
    ):
        raise ValueError("Graph geographic IDs must be unique nonempty strings")

    for column in PopulationColumn:
        if (
            not pd.api.types.is_integer_dtype(units_df[column])
            or bool(units_df[column].isna().any())
            or bool(units_df[column].lt(0).any())
        ):
            raise ValueError(f"Graph {column} must contain nonnegative integer counts")

    expected_poc = units_df[PopulationColumn.TOTAL] - units_df[PopulationColumn.NON_HISPANIC_WHITE]
    white_black_population = (
        units_df[PopulationColumn.NON_HISPANIC_WHITE]
        + units_df[PopulationColumn.NON_HISPANIC_BLACK]
    )

    if not bool(units_df[PopulationColumn.POC].eq(expected_poc).all()) or bool(
        white_black_population.gt(units_df[PopulationColumn.TOTAL]).any()
    ):
        raise ValueError("Graph population definitions disagree")

    if (
        units_df.crs is None
        or units_df.geometry.isna().any()
        or units_df.geometry.is_empty.any()
        or not units_df.geometry.is_valid.all()
        or not units_df.geom_type.isin(["Polygon", "MultiPolygon"]).all()
    ):
        raise ValueError("Graph geometries must be valid, nonempty polygons with a defined CRS")
