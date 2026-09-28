"""Exercise the public graph and numerical interfaces independently of study configuration."""

from copy import deepcopy

import capy_metrics as metrics
import networkx as nx
import numpy as np
import pytest
from national_pipeline.compute_metrics import calculate_scores
from national_pipeline.compute_metrics.metric_types import MetricName, PopulationComparison
from scipy import sparse


def build_custom_population_graph() -> nx.Graph:
    """Return a plain NetworkX graph with mixed node labels and custom population attributes."""
    graph = nx.path_graph(["first", 42, ("third",)])

    for node, group, total, coordinates in zip(
        graph, (2, 7, 4), (10, 12, 20), ((0, 0), (3, 0), (3, 4))
    ):
        graph.nodes[node].update(
            group=group,
            other=total - group,
            residents=total,
            east=coordinates[0],
            north=coordinates[1],
        )

    return graph


def test_public_graph_functions_match_numerical_functions_without_mutating_inputs():
    graph = build_custom_population_graph()
    original_graph = deepcopy(graph)
    group = np.array([2.0, 7.0, 4.0])
    totals = np.array([10.0, 12.0, 20.0])
    adjacency = metrics.build_csr_adjacency_matrix(graph)
    original_adjacency = adjacency.copy()
    shares = group / totals

    for weight_type in metrics.MoranWeightType:
        graph_score = metrics.morans_I_from_graph(
            graph, "group", "residents", weight_type, centroid_attributes=("east", "north")
        )

        if weight_type in (
            metrics.MoranWeightType.INVERSE_DISTANCE,
            metrics.MoranWeightType.INVERSE_SQUARED_DISTANCE,
        ):
            power = 1 if weight_type == metrics.MoranWeightType.INVERSE_DISTANCE else 2
            numerical_score = metrics.distance_morans_I(
                np.array([(0, 0), (3, 0), (3, 4)]), shares, power
            )
        else:
            weights = metrics.build_moran_weights(adjacency, weight_type)
            numerical_score = metrics.morans_I(sparse.csr_matrix(weights), shares)

        assert graph_score == pytest.approx(numerical_score)

    for from_graph, from_arrays in (
        (metrics.dissimilarity_from_graph, metrics.dissimilarity),
        (metrics.entropy_index_from_graph, metrics.entropy_index),
        (metrics.relative_diversity_from_graph, metrics.relative_diversity),
    ):
        for weights in (None, adjacency + sparse.eye_array(3)):
            assert from_graph(
                graph, "group", "residents", spatial_weights=weights
            ) == pytest.approx(from_arrays(group, totals, spatial_weights=weights))

    assert metrics.aspatial_capy_from_graph(graph, "group", "other") == pytest.approx(
        metrics.aspatial_capy(group, totals - group)
    )
    assert metrics.edge_assortativity_from_graph(graph, "group", "residents") == pytest.approx(
        metrics.edge_assortativity(adjacency, group, totals)
    )
    assert metrics.half_edge_assortativity_from_graph(graph, "group", "residents") == pytest.approx(
        metrics.half_edge_assortativity(adjacency, group, totals)
    )
    assert nx.utils.graphs_equal(graph, original_graph)
    assert (adjacency != original_adjacency).nnz == 0
    np.testing.assert_array_equal(group, [2, 7, 4])
    np.testing.assert_array_equal(totals, [10, 12, 20])


def test_lambda_weights_neighbor_pairs_and_exact_scores_remove_only_self_pairs():
    graph = nx.path_graph(2)
    graph.nodes[0].update(first=4, second=3)
    graph.nodes[1].update(first=2, second=2)
    adjacency = metrics.build_csr_adjacency_matrix(graph)
    first_population = np.array([4, 2])
    second_population = np.array([3, 2])
    people = [
        (node, person < graph.nodes[node]["first"])
        for node in graph
        for person in range(graph.nodes[node]["first"] + graph.nodes[node]["second"])
    ]

    for lam in (0, 1, 2.5):
        for exact in (False, True):
            first_pairs = between_pairs = second_pairs = 0.0

            for first_index, (first_node, first_group) in enumerate(people):
                for second_index, (second_node, second_group) in enumerate(people):
                    if exact and first_index == second_index:
                        continue

                    weight = 1 if first_node == second_node else lam
                    first_pairs += weight * (first_group and second_group)
                    between_pairs += weight * (first_group and not second_group)
                    second_pairs += weight * (not first_group and not second_group)

            expected = 0.5 * (
                first_pairs / (first_pairs + between_pairs)
                + second_pairs / (second_pairs + between_pairs)
            )
            numerical_function = metrics.capy_exact if exact else metrics.capy
            graph_function = metrics.capy_exact_from_graph if exact else metrics.capy_from_graph

            assert numerical_function(
                adjacency, first_population, second_population, lam
            ) == pytest.approx(expected)
            assert graph_function(graph, "first", "second", lam) == pytest.approx(expected)

    assert metrics.capy(adjacency, first_population, second_population, 0) == metrics.aspatial_capy(
        first_population, second_population
    )
    assert metrics.aspatial_capy(np.array([1]), np.array([1])) == 0.5
    assert metrics.capy_exact(sparse.csr_array((1, 1)), np.array([1]), np.array([1]), 0) == 0

    with pytest.raises(ValueError, match="lam"):
        metrics.capy(adjacency, first_population, second_population, -1)

    with pytest.raises(ValueError, match="integer"):
        metrics.capy_exact(adjacency, np.array([0.5, 2]), second_population)


def test_public_functions_distinguish_invalid_inputs_from_undefined_scores():
    graph = build_custom_population_graph()
    graph.remove_edges_from(list(graph.edges))

    # Aspatial functions need no connectivity or adjacency at all.
    assert np.isfinite(metrics.dissimilarity_from_graph(graph, "group", "residents"))

    with pytest.raises(metrics.UndefinedMetricError) as undefined:
        metrics.morans_I_from_graph(graph, "group", "residents")

    assert undefined.value.reason == metrics.UndefinedMetricReason.NO_NEIGHBORS

    with pytest.raises(metrics.UndefinedMetricError) as undefined:
        metrics.morans_I(sparse.eye_array(2), np.array([0.5, 0.5]))

    assert undefined.value.reason == metrics.UndefinedMetricReason.ZERO_SHARE_VARIANCE

    with pytest.raises(ValueError, match="matching"):
        metrics.morans_I(sparse.eye_array(3), np.array([0.2, 0.6]))

    with pytest.raises(ValueError, match="positive"):
        metrics.dissimilarity(np.array([1, 0]), np.array([1, 0]))

    with pytest.raises(KeyError):
        metrics.morans_I_from_graph(graph, "missing", "residents")


def test_pipeline_prepares_each_requested_weight_once_and_skips_unrequested_formulas(monkeypatch):
    graph = build_custom_population_graph()

    for node in graph:
        graph.nodes[node].update(
            WHITE=graph.nodes[node]["group"],
            BLACK=graph.nodes[node]["other"],
            POC=graph.nodes[node]["other"] + 2,
        )

    build_adjacency = calculate_scores.build_csr_adjacency_matrix
    build_weights = calculate_scores.build_moran_weights
    adjacency_calls = []
    weight_calls = []

    def count_adjacency_build(graph):
        adjacency_calls.append(True)
        return build_adjacency(graph)

    def count_weight_build(adjacency, weight_type):
        weight_calls.append(weight_type)
        return build_weights(adjacency, weight_type)

    def reject_unrequested_score(*args, **kwargs):
        raise AssertionError("Unrequested population score was computed")

    monkeypatch.setattr(calculate_scores, "build_csr_adjacency_matrix", count_adjacency_build)
    monkeypatch.setattr(calculate_scores, "build_moran_weights", count_weight_build)
    monkeypatch.setattr(calculate_scores, "dissimilarity", reject_unrequested_score)
    scores = calculate_scores.calculate_graph_metrics(
        graph,
        tuple(PopulationComparison),
        (MetricName.MORAN_ADJACENCY, MetricName.MORAN_ROW_STANDARDIZED),
    )

    assert len(scores) == 2
    assert len(adjacency_calls) == 1
    assert weight_calls == [
        metrics.MoranWeightType.ADJACENCY,
        metrics.MoranWeightType.ROW_STANDARDIZED,
    ]


def test_exact_capy_preserves_small_neighbor_contributions():
    adjacency = metrics.build_csr_adjacency_matrix(nx.path_graph(3))
    first_population = np.array([1, 1, 0])
    second_population = np.array([0, 0, 1])

    # All eligible pairs cross unit boundaries, so changing a positive lambda cancels in the ratios.
    assert metrics.capy_exact(
        adjacency, first_population, second_population, lam=1e-16
    ) == pytest.approx(1 / 3)


def test_csr_duplicate_entries_are_combined_without_mutating_caller_storage():
    adjacency = sparse.csr_array(([0.5, 0.5, 0.5, 0.5], [1, 1, 0, 0], [0, 2, 4]), shape=(2, 2))
    original_data = adjacency.data.copy()
    original_indices = adjacency.indices.copy()
    original_indptr = adjacency.indptr.copy()

    assert metrics.morans_I(adjacency, np.array([0.2, 0.8])) == pytest.approx(-1)
    weights = metrics.build_moran_weights(adjacency, metrics.MoranWeightType.ADJACENCY)
    np.testing.assert_array_equal(weights.toarray(), [[0, 1], [1, 0]])
    np.testing.assert_array_equal(adjacency.data, original_data)
    np.testing.assert_array_equal(adjacency.indices, original_indices)
    np.testing.assert_array_equal(adjacency.indptr, original_indptr)

    duplicated_ones = sparse.csr_array(
        ([1.0, 1.0, 1.0, 1.0], [1, 1, 0, 0], [0, 2, 4]), shape=(2, 2)
    )

    with pytest.raises(ValueError, match="binary"):
        metrics.build_moran_weights(duplicated_ones, metrics.MoranWeightType.ADJACENCY)


def test_relative_majority_ties_do_not_depend_on_population_array_dtype():
    graph = nx.path_graph(3)
    nx.set_node_attributes(graph, dict(enumerate([1, 0, 2])), "group")
    nx.set_node_attributes(graph, 10, "total")
    adjacency = metrics.build_csr_adjacency_matrix(graph)

    for numerical_function, graph_function in (
        (
            metrics.edge_assortativity,
            metrics.edge_assortativity_from_graph,
        ),
        (
            metrics.half_edge_assortativity,
            metrics.half_edge_assortativity_from_graph,
        ),
    ):
        graph_score = graph_function(graph, "group", "total")

        assert graph_score == 0

        for dtype in (np.float32, np.float64):
            group_population = np.array([1, 0, 2], dtype=dtype)
            total_population = np.array([10, 10, 10], dtype=dtype)

            assert numerical_function(adjacency, group_population, total_population) == graph_score
