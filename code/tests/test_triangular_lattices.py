"""Finite and periodic triangular-lattice scientific contracts."""

import numpy as np
import pytest
from experiments.experiment_scores import calculate_experiment_scores
from experiments.reardon_osullivan.plot_triangular_lattices import plot_triangular_lattices
from experiments.reardon_osullivan.triangular_lattices import (
    PRINTED_PATTERNS,
    build_triangular_adjacency,
    build_triangular_lattice_results,
)


def test_triangular_repeat_has_six_neighbors_and_preserves_the_printed_seam_pair():
    pattern = np.array([[int(value) for value in row] for row in PRINTED_PATTERNS["upper_left"]])
    black = pattern.ravel()
    printed = build_triangular_adjacency(*pattern.shape, periodic=False)
    repeated = build_triangular_adjacency(*pattern.shape, periodic=True)
    assert black.sum() == 18
    assert black @ (printed @ black) == 0
    assert black @ (repeated @ black) == 2
    np.testing.assert_array_equal(repeated.sum(axis=1), np.full(120, 6))

    independent_period = np.tile([[1, 0, 0], [0, 0, 1]], (2, 1)).ravel()
    adjacency = build_triangular_adjacency(4, 3, periodic=True)
    scores = calculate_experiment_scores(
        adjacency, independent_period, 1 - independent_period, distinct_people=True
    )
    assert scores.metric_values["capy_exact"] == pytest.approx(0.25)
    assert scores.metric_values["spatial_relative_diversity"] == pytest.approx(4 / 49)


def test_triangular_lattices_exports_four_saved_printed_windows(tmp_path):
    scores_df, windows = build_triangular_lattice_results()
    assert len(scores_df) == 8
    np.savez_compressed(tmp_path / "triangular_windows.npz", **windows)
    output_directory = tmp_path / "figures"
    plot_triangular_lattices(tmp_path, output_directory)

    assert {path.name for path in output_directory.iterdir()} == {
        "dispersed_sparse_population.png",
        "dispersed_denser_population.png",
        "large_population_clusters.png",
        "small_population_clusters.png",
    }
