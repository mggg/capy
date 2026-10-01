"""Choose the study's metric functions and reuse prepared graph weights across comparisons."""

import networkx as nx
import numpy as np
from capy_metrics import (
    MoranWeightType,
    UndefinedMetricError,
    aspatial_capy,
    build_csr_adjacency_matrix,
    build_moran_weights,
    capy,
    capy_exact,
    dissimilarity,
    distance_morans_I,
    edge_assortativity,
    entropy_index,
    half_edge_assortativity,
    morans_I,
    node_attribute_to_numpy_arr,
    population_shares,
    relative_diversity,
)
from gerrychain import Graph
from scipy import sparse

from national_pipeline.build_graphs.construct_graph import GraphNodeAttribute
from national_pipeline.population_table_columns import PopulationColumn

from .metric_types import MetricName, MetricValue, PopulationComparison

MORAN_WEIGHT_TYPES = {
    MetricName.MORAN_ADJACENCY: MoranWeightType.ADJACENCY,
    MetricName.MORAN_WITH_SELF: MoranWeightType.WITH_SELF,
    MetricName.MORAN_ROW_STANDARDIZED: MoranWeightType.ROW_STANDARDIZED,
    MetricName.MORAN_NEGATIVE_LAPLACIAN: MoranWeightType.NEGATIVE_LAPLACIAN,
    MetricName.MORAN_METROPOLIS: MoranWeightType.METROPOLIS,
}
DISTANCE_POWERS = {
    MetricName.MORAN_INVERSE_DISTANCE: 1,
    MetricName.MORAN_INVERSE_SQUARED_DISTANCE: 2,
}
SPATIAL_EVENNESS_METRICS = (
    MetricName.SPATIAL_DISSIMILARITY,
    MetricName.SPATIAL_ENTROPY_INDEX,
    MetricName.SPATIAL_RELATIVE_DIVERSITY,
)
ADJACENCY_METRICS = (
    MetricName.CAPY,
    MetricName.CAPY_EXACT,
    MetricName.EDGE_ASSORTATIVITY,
    MetricName.HALF_EDGE_ASSORTATIVITY,
)


def calculate_graph_metrics(
    graph: Graph,
    comparisons: tuple[PopulationComparison, ...],
    metric_names: tuple[MetricName, ...],
) -> dict[PopulationComparison, dict[MetricName, MetricValue]]:
    """Calculate selected study scores for each population comparison.

    Args:
        graph (Graph): Connected graph already checked against its archive population accounting.
            Distance scores require finite centroids in ESRI:102003. Inputs are unchanged.
        comparisons (tuple[PopulationComparison, ...]): White–Black and/or White–POC comparisons.
            Each comparison uses its own combined population as the denominator.
        metric_names (tuple[MetricName, ...]): Scores to calculate; unrequested scores are not run.

    Returns:
        dict[PopulationComparison, dict[MetricName, MetricValue]]: Scores or undefined reasons.
            One undefined score does not discard any other result.

    Raises:
        KeyError: A required population or coordinate attribute is absent.
        ValueError: The graph, coordinates, or numeric inputs/results are invalid. Only
            UndefinedMetricError is converted to a saved reason; other errors stop the run.
    """
    if not graph or graph.is_directed() or graph.is_multigraph() or nx.number_of_selfloops(graph):
        raise ValueError(
            "Study metrics require a nonempty undirected simple graph without self-loops"
        )

    if not nx.is_connected(graph):
        raise ValueError("Study metrics require a connected graph")

    weights_by_metric, coordinates = _prepare_selected_weights(graph, metric_names)
    first_population = node_attribute_to_numpy_arr(graph, PopulationColumn.NON_HISPANIC_WHITE)
    comparison_scores = {}

    for comparison in dict.fromkeys(comparisons):
        second_population = node_attribute_to_numpy_arr(graph, comparison.second_population_column)
        scores: dict[MetricName, MetricValue] = {}

        for metric in dict.fromkeys(metric_names):
            try:
                value = _calculate_selected_metric(
                    metric, first_population, second_population, weights_by_metric, coordinates
                )

                if not np.isfinite(value):
                    raise ValueError(f"Metric produced an unexpected nonfinite value: {metric}")

                scores[metric] = value
            except UndefinedMetricError as error:
                scores[metric] = error.reason

        comparison_scores[comparison] = scores

    return comparison_scores


def _prepare_selected_weights(
    graph: Graph, metric_names: tuple[MetricName, ...]
) -> tuple[dict[MetricName, sparse.csr_array], np.ndarray | None]:
    """Build only requested weights and read centroids once, in the same graph node order.

    Returns a weight matrix for each requested adjacency-based score, plus coordinates when
    distance scores are selected. Shared matrices are read-only by convention. Invalid graph
    structure or distance coordinates raise ValueError; missing coordinate attributes raise KeyError.
    """
    weights_by_metric = {}
    coordinates = None
    adjacency_metrics = (
        set(MORAN_WEIGHT_TYPES) | set(SPATIAL_EVENNESS_METRICS) | set(ADJACENCY_METRICS)
    )

    if any(metric in adjacency_metrics for metric in metric_names):
        adjacency = build_csr_adjacency_matrix(graph)
        local_environment = None

        for metric in dict.fromkeys(metric_names):
            if metric in MORAN_WEIGHT_TYPES:
                weights_by_metric[metric] = build_moran_weights(
                    adjacency, MORAN_WEIGHT_TYPES[metric]
                )
            elif metric in SPATIAL_EVENNESS_METRICS:
                if local_environment is None:
                    local_environment = adjacency + sparse.eye_array(len(graph), format="csr")

                weights_by_metric[metric] = local_environment
            elif metric in ADJACENCY_METRICS:
                weights_by_metric[metric] = adjacency

    if any(metric in DISTANCE_POWERS for metric in metric_names):
        coordinates = np.column_stack(
            [
                node_attribute_to_numpy_arr(graph, attribute)
                for attribute in (GraphNodeAttribute.CENTROID_X, GraphNodeAttribute.CENTROID_Y)
            ]
        )

        if graph.graph.get("crs") != "ESRI:102003" or not np.isfinite(coordinates).all():
            raise ValueError("Study distance metrics require finite centroids in ESRI:102003")

    return weights_by_metric, coordinates


def _calculate_selected_metric(
    metric: MetricName,
    first_population: np.ndarray,
    second_population: np.ndarray,
    weights_by_metric: dict[MetricName, sparse.csr_array],
    coordinates: np.ndarray | None,
) -> float:
    """Apply the selected public numerical function to one study population comparison.

    Population totals refer to the two comparison groups, not necessarily every resident.
    """
    total_population = first_population + second_population

    if metric in MORAN_WEIGHT_TYPES:
        return morans_I(
            weights_by_metric[metric], population_shares(first_population, total_population)
        )

    if metric in DISTANCE_POWERS:
        assert coordinates is not None
        return distance_morans_I(
            coordinates,
            population_shares(first_population, total_population),
            DISTANCE_POWERS[metric],
        )

    spatial_weights = weights_by_metric.get(metric) if metric in SPATIAL_EVENNESS_METRICS else None

    match metric:
        case MetricName.DISSIMILARITY | MetricName.SPATIAL_DISSIMILARITY:
            return dissimilarity(
                first_population, total_population, spatial_weights=spatial_weights
            )
        case MetricName.ENTROPY_INDEX | MetricName.SPATIAL_ENTROPY_INDEX:
            return entropy_index(
                first_population, total_population, spatial_weights=spatial_weights
            )
        case MetricName.RELATIVE_DIVERSITY | MetricName.SPATIAL_RELATIVE_DIVERSITY:
            return relative_diversity(
                first_population, total_population, spatial_weights=spatial_weights
            )
        case MetricName.ASPATIAL_CAPY:
            return aspatial_capy(first_population, second_population)
        case MetricName.CAPY:
            return capy(weights_by_metric[metric], first_population, second_population, lam=1)
        case MetricName.CAPY_EXACT:
            return capy_exact(weights_by_metric[metric], first_population, second_population, lam=1)
        case MetricName.EDGE_ASSORTATIVITY:
            return edge_assortativity(weights_by_metric[metric], first_population, total_population)
        case MetricName.HALF_EDGE_ASSORTATIVITY:
            return half_edge_assortativity(
                weights_by_metric[metric], first_population, total_population
            )

    raise ValueError(f"Unsupported study metric: {metric}")
