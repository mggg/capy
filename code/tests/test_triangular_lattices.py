"""Finite and periodic triangular-lattice scientific contracts."""

import matplotlib.pyplot as plt
import numpy as np
import pytest
from experiments.experiment_scores import calculate_example_scores
from experiments.reardon_osullivan.plot_triangular_lattices import plot_triangular_lattice
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
    scores = calculate_example_scores(
        adjacency, independent_period, 1 - independent_period, distinct_people=True
    )
    assert scores["capy_exact"] == pytest.approx(0.25)
    assert scores["spatial_relative_diversity"] == pytest.approx(4 / 49)


def test_triangular_lattice_draws_saved_window_on_caller_axes():
    scores_df, windows = build_triangular_lattice_results()
    assert len(scores_df) == 8
    window = windows["printed_upper_left"]
    original = window.copy()
    figure, axes = plt.subplots(1, 2)
    try:
        figure_numbers = plt.get_fignums()
        plot_triangular_lattice(axes[0], window)
        assert len(axes[0].collections[0].get_offsets()) == window.size
        assert not axes[1].collections
        assert plt.get_fignums() == figure_numbers
        np.testing.assert_array_equal(window, original)
    finally:
        plt.close(figure)
