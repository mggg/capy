"""Scientific formula checks, undefined outcomes, archive inputs, and complete-history means."""

from copy import deepcopy
from zipfile import ZipFile

import networkx as nx
import numpy as np
import pandas as pd
import pytest
from capy_core.compute_metrics.calculate_scores import calculate_graph_metrics
from capy_core.compute_metrics.metric_types import (
    MetricName,
    PopulationComparison,
    UndefinedMetricReason,
)
from capy_core.compute_metrics.run_metrics import compute_metrics
from capy_core.compute_metrics.summarize_years import average_when_all_years_present
from capy_core.geography_types import GeographyLevel, StudyAreaType
from capy_core.pipeline_config import PipelineConfig
from capy_metrics import distance_morans_I
from gerrychain import Graph
from scipy.spatial.distance import cdist


def build_example_graph() -> Graph:
    """Three adjacent units with 2/8, 7/3, and 4/6 White/Black counts and known coordinates."""
    graph = Graph(nx.path_graph(["a", "b", "c"]))

    for node, white, coordinates in zip(graph, (2, 7, 4), ((0, 0), (3, 0), (3, 4))):
        graph.nodes[node].update(
            WHITE=white,
            BLACK=10 - white,
            TOTPOP=10,
            POC=10 - white,
            centroid_x=coordinates[0],
            centroid_y=coordinates[1],
        )

    graph.graph["crs"] = "ESRI:102003"

    return graph


def test_population_scores_match_independent_reference_and_leave_graph_unchanged():
    graph = build_example_graph()
    original = deepcopy(graph)
    scores = calculate_graph_metrics(graph, (PopulationComparison.WHITE_BLACK,), tuple(MetricName))[
        PopulationComparison.WHITE_BLACK
    ]
    # These fixed values also match moon-capy's build_nine_scores.py on the same counts and path.
    expected = {
        MetricName.DISSIMILARITY: 0.3619909502262442,
        MetricName.THEIL_INFORMATION: 0.13076314998687977,
        MetricName.RELATIVE_DIVERSITY: 0.171945701357466,
        MetricName.ASPATIAL_CAPY: 0.5859728506787331,
        MetricName.SPATIAL_DISSIMILARITY: 0.0904977375565611,
        MetricName.SPATIAL_THEIL_INFORMATION: -0.003806749683755717,
        MetricName.SPATIAL_RELATIVE_DIVERSITY: -0.005279034690799378,
        MetricName.CAPY_EXACT: 0.4701119739769975,
        MetricName.MORAN_WITH_SELF: -0.052631578947368314,
        MetricName.MORAN_ROW_STANDARDIZED: -0.8421052631578945,
    }

    for metric, value in expected.items():
        assert scores[metric] == pytest.approx(value, abs=1e-14)

    assert nx.utils.graphs_equal(graph, original)

    # Every unit has ten people: enumerate distinct ordered endpoint pairs independently.
    people = [(node, person < graph.nodes[node]["WHITE"]) for node in graph for person in range(10)]
    first_group_pairs = second_group_pairs = between_group_pairs = 0

    for first_index, (first_node, first_white) in enumerate(people):
        for second_index, (second_node, second_white) in enumerate(people):
            if first_index == second_index or not (
                first_node == second_node or graph.has_edge(first_node, second_node)
            ):
                continue

            first_group_pairs += first_white and second_white
            second_group_pairs += not first_white and not second_white
            between_group_pairs += first_white and not second_white

    direct_capy = 0.5 * (
        first_group_pairs / (first_group_pairs + between_group_pairs)
        + second_group_pairs / (second_group_pairs + between_group_pairs)
    )

    assert scores[MetricName.CAPY_EXACT] == pytest.approx(direct_capy)

    # Additional residents change the White–POC denominator and its weights, but not White–Black.
    graph.nodes["c"].update(TOTPOP=20, POC=16)
    white_poc_scores = calculate_graph_metrics(
        graph, (PopulationComparison.WHITE_POC,), tuple(MetricName)
    )[PopulationComparison.WHITE_POC]
    white_black_scores = calculate_graph_metrics(
        graph, (PopulationComparison.WHITE_BLACK,), tuple(MetricName)
    )[PopulationComparison.WHITE_BLACK]

    assert white_poc_scores[MetricName.DISSIMILARITY] == pytest.approx(50 / 117)
    assert white_black_scores == scores


def test_moran_variants_match_dense_formulas_and_assortativity_matches_edge_counts():
    graph = build_example_graph()
    scores = calculate_graph_metrics(graph, (PopulationComparison.WHITE_BLACK,), tuple(MetricName))[
        PopulationComparison.WHITE_BLACK
    ]
    adjacency = nx.to_numpy_array(graph, weight=None)
    degrees = adjacency.sum(axis=1)
    metropolis = np.zeros_like(adjacency)

    for first, second in zip(*np.nonzero(adjacency)):
        metropolis[first, second] = 1 / max(degrees[first], degrees[second])

    np.fill_diagonal(metropolis, 1 - metropolis.sum(axis=1))
    weights_by_metric = {
        MetricName.MORAN_ADJACENCY: adjacency,
        MetricName.MORAN_NEGATIVE_LAPLACIAN: adjacency - np.diag(degrees),
        MetricName.MORAN_METROPOLIS: metropolis,
    }
    shares = np.array([0.2, 0.7, 0.4])
    centered = shares - shares.mean()

    for metric, weights in weights_by_metric.items():
        expected = (
            3
            / np.abs(weights).sum()
            * sum(
                centered[first] * weights[first, second] * centered[second]
                for first in range(3)
                for second in range(3)
            )
            / sum(centered**2)
        )

        assert scores[metric] == pytest.approx(expected)

    assert scores[MetricName.EDGE_ASSORTATIVITY] == 0
    assert scores[MetricName.HALF_EDGE_ASSORTATIVITY] == 0

    graph.add_edge("a", "c")
    scores = calculate_graph_metrics(graph, (PopulationComparison.WHITE_BLACK,), tuple(MetricName))[
        PopulationComparison.WHITE_BLACK
    ]
    # One first-class unit and two second-class units: one same-class edge and two mixed edges.
    assert scores[MetricName.EDGE_ASSORTATIVITY] == pytest.approx(1 / 6)
    assert scores[MetricName.HALF_EDGE_ASSORTATIVITY] == pytest.approx(1 / 4)

    nx.set_node_attributes(graph, {"a": 0, "b": 1, "c": 0}, "class")
    expected_half = (1 + nx.attribute_assortativity_coefficient(graph, "class")) / 2

    assert scores[MetricName.HALF_EDGE_ASSORTATIVITY] == pytest.approx(expected_half)


def test_distance_batches_match_dense_weights_and_coincident_centroids_only_affect_distance_scores():
    rng = np.random.default_rng(5)
    coordinates = rng.random((1001, 2))
    shares = rng.random(1001)
    distances = cdist(coordinates, coordinates)
    np.fill_diagonal(distances, np.inf)
    centered = shares - shares.mean()

    for metric, power in (
        (MetricName.MORAN_INVERSE_DISTANCE, 1),
        (MetricName.MORAN_INVERSE_SQUARED_DISTANCE, 2),
    ):
        weights = distances ** (-power)
        weights /= weights.sum(axis=1, keepdims=True)
        expected = centered @ weights @ centered / (centered @ centered)

        assert distance_morans_I(coordinates, shares, power) == pytest.approx(expected, abs=1e-14)

    graph = build_example_graph()
    graph.nodes["b"].update(centroid_x=0, centroid_y=0)
    scores = calculate_graph_metrics(graph, (PopulationComparison.WHITE_BLACK,), tuple(MetricName))[
        PopulationComparison.WHITE_BLACK
    ]

    assert scores[MetricName.MORAN_INVERSE_DISTANCE] == UndefinedMetricReason.COINCIDENT_CENTROIDS
    assert isinstance(scores[MetricName.MORAN_ROW_STANDARDIZED], float)
    assert isinstance(scores[MetricName.DISSIMILARITY], float)


def test_single_node_and_absent_group_keep_defined_metrics():
    graph = build_example_graph().subgraph(["a"]).copy()
    scores = calculate_graph_metrics(graph, (PopulationComparison.WHITE_BLACK,), tuple(MetricName))[
        PopulationComparison.WHITE_BLACK
    ]

    assert scores[MetricName.DISSIMILARITY] == 0
    assert scores[MetricName.ASPATIAL_CAPY] == pytest.approx(0.5)
    assert scores[MetricName.MORAN_ROW_STANDARDIZED] == UndefinedMetricReason.ZERO_SHARE_VARIANCE
    assert isinstance(scores[MetricName.CAPY_EXACT], float)

    graph.nodes["a"].update(WHITE=0, BLACK=10, POC=10)
    scores = calculate_graph_metrics(graph, (PopulationComparison.WHITE_BLACK,), tuple(MetricName))[
        PopulationComparison.WHITE_BLACK
    ]

    assert scores[MetricName.DISSIMILARITY] == UndefinedMetricReason.ABSENT_POPULATION_GROUP
    assert scores[MetricName.CAPY_EXACT] == UndefinedMetricReason.NO_PAIR_INTERACTIONS


def test_complete_history_means_use_a_separate_fixed_cohort_for_each_metric():
    rows = []

    for metric in ("dissimilarity", "moran_row_standardized"):
        for area, year, value in (
            ("a", 2000, 0.2),
            ("a", 2010, 0.4),
            ("b", 2000, 0.8),
            ("b", 2010, 0.6),
        ):
            if metric == "moran_row_standardized" and area == "b" and year == 2010:
                value = None

            rows.append(
                {
                    "study_area_id": area,
                    "census_year": year,
                    "geography_level": "tracts",
                    "population_comparison": "white_black",
                    "metric": metric,
                    "value": value,
                }
            )

    means_df = average_when_all_years_present(
        pd.DataFrame(rows), {GeographyLevel.TRACT: (2000, 2010)}
    )

    assert means_df.loc[
        means_df.metric.eq("dissimilarity"), "average_when_all_years_present"
    ].tolist() == pytest.approx([0.5, 0.5])
    assert means_df.loc[
        means_df.metric.eq("moran_row_standardized"), "average_when_all_years_present"
    ].tolist() == pytest.approx([0.2, 0.4])
    assert means_df.loc[
        means_df.metric.eq("moran_row_standardized"), "contributing_area_ids"
    ].tolist() == [["a"], ["a"]]

    empty_df = average_when_all_years_present(
        pd.DataFrame(rows), {GeographyLevel.TRACT: (1990, 2000, 2010)}
    )

    assert empty_df.average_when_all_years_present.isna().all()
    assert empty_df.area_count.eq(0).all()


def test_archive_to_metrics_preserves_no_graph_rows_and_invalidates_failed_rerun(tmp_path):
    config = PipelineConfig(
        census_geography_years=(2020,),
        census_geography_levels=(GeographyLevel.TRACT,),
        study_area_type=StudyAreaType.COUNTY,
        graph_archive_directory=tmp_path / "graphs",
        metric_results_directory=tmp_path / "results",
    )
    config.graph_archive_directory.mkdir()
    archive_path = config.graph_archive_directory / "county_2020_2020_tracts.zip"
    graph = build_example_graph()
    graph.graph.update(
        study_area_id="county_10001",
        study_area_type="county",
        definition_year=2020,
        census_year=2020,
        geography_level="tracts",
        input_population={"TOTPOP": 30, "WHITE": 13, "BLACK": 17, "POC": 17},
        retained_population={"TOTPOP": 30, "WHITE": 13, "BLACK": 17, "POC": 17},
        removed_population={"TOTPOP": 0, "WHITE": 0, "BLACK": 0, "POC": 0},
    )
    graph_path = tmp_path / "graph.json"
    graph.to_json(str(graph_path))
    summary_rows = []

    for area, status in (("county_10001", "ready"), ("county_10003", "no_units_selected")):
        ready = status == "ready"
        row = {
            "study_area_id": area,
            "census_year": 2020,
            "geography_level": "tracts",
            "status": status,
            "graph_member": f"graphs/{area}.json" if ready else None,
            "node_count": 3 if ready else 0,
            "edge_count": 2 if ready else 0,
        }

        for group in ("input", "retained", "removed"):
            for column, count in graph.graph[f"{group}_population"].items():
                row[f"{group}_{column}"] = count if ready else 0

        summary_rows.append(row)

    summary_df = pd.DataFrame(summary_rows)

    with ZipFile(archive_path, "w") as archive:
        archive.writestr("summary.csv", summary_df.to_csv(index=False))
        archive.write(graph_path, "graphs/county_10001.json")

    scores_df = compute_metrics(config, tmp_path)

    assert len(scores_df) == 2 * 2 * len(MetricName)
    assert (
        scores_df.loc[scores_df.study_area_id.eq("county_10003"), "undefined_reason"]
        .eq("no_graph")
        .all()
    )

    result_directory = config.metric_results_directory / "county/2020"

    assert (result_directory / "average_when_all_years_present.parquet").is_file()

    summary_df.loc[0, "edge_count"] = 99

    with ZipFile(archive_path, "w") as archive:
        archive.writestr("summary.csv", summary_df.to_csv(index=False))
        archive.write(graph_path, "graphs/county_10001.json")

    with pytest.raises(ValueError, match="node or edge counts"):
        compute_metrics(config, tmp_path)

    assert not list(result_directory.glob("*.parquet"))
