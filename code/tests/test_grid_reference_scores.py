"""Analytic checkerboard scores against periodic lattice calculations."""

import networkx as nx
import numpy as np
import pytest
from experiments.experiment_scores import calculate_experiment_scores
from experiments.grid_configurations.grid_reference_scores import build_grid_reference_scores


def test_analytic_checkerboard_curves_match_periodic_score_calculations():
    graph = nx.grid_2d_graph(8, 8, periodic=True)
    adjacency = nx.to_scipy_sparse_array(graph, format="csr")
    shares = np.array([0.125, 0.25, 0.5])
    curves_df = build_grid_reference_scores(shares)
    checkerboard_df = curves_df.loc[curves_df.arrangement.eq("checkerboard")]

    for share in shares:
        first = np.array([2 * share if (row + column) % 2 else 0 for row, column in graph])
        calculated = calculate_experiment_scores(adjacency, first, 1 - first).to_record()

        for _, curve in checkerboard_df.loc[checkerboard_df.group_share.eq(share)].iterrows():
            assert calculated[curve.metric] == pytest.approx(curve.value, abs=1e-12)
