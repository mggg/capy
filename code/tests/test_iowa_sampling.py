"""Random-stream ownership and failed attempts in county-configuration sampling."""

import random

import networkx as nx
import numpy as np
from experiments.iowa_configurations import county_configurations as iowa


def test_county_sampling_advances_one_stream_across_targets_and_reseeds_each_sample(monkeypatch):
    graph = nx.path_graph(["a", "b", "c"])
    nx.set_node_attributes(graph, {"a": 10, "b": 20, "c": 30}, "TOTPOP")
    random_draws = []

    def select_first_county(graph, target_share, arrangement, rng):
        random_draws.append(rng.random())
        return {"a"}

    monkeypatch.setattr(iowa, "select_county_arrangement", select_first_county)
    results = iowa.sample_county_configurations(
        graph, iowa.CountyArrangement.CLUSTERED, np.array([0.1, 0.3]), 2, 42
    )
    expected_draws = []

    for seed in (42, 43):
        rng = random.Random(seed)
        expected_draws.extend([rng.random(), rng.random()])

    assert random_draws == expected_draws
    assert [(result.sample, result.seed, result.target_share) for result in results] == [
        (0, 42, 0.1),
        (0, 42, 0.3),
        (1, 43, 0.1),
        (1, 43, 0.3),
    ]
    assert all(result.configuration.group_share == 1 / 6 for result in results)
    assert all(result.configuration.component_count == 1 for result in results)
    assert dict(nx.get_node_attributes(graph, "TOTPOP")) == {"a": 10, "b": 20, "c": 30}


def test_failed_county_selection_keeps_attempt_metadata_without_scores(monkeypatch):
    graph = nx.path_graph(["a", "b", "c"])
    nx.set_node_attributes(graph, 100, "TOTPOP")
    monkeypatch.setattr(iowa, "select_county_arrangement", lambda *args: None)
    results = iowa.sample_county_configurations(
        graph, iowa.CountyArrangement.CLUSTERED, np.array([0.2]), 1, 42
    )
    (result,) = results
    assert result.configuration is None
    assert result.to_record() == {
        "arrangement": "clustered",
        "sample": 0,
        "seed": 42,
        "target_share": 0.2,
        "status": "no_multicluster_sample",
    }
