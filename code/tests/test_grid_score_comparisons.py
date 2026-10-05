"""Prepared grid-score-comparisons categories, reference scores, and plotted values."""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from experiments.experiment_scores import calculate_experiment_scores
from experiments.grid_configurations import grid_score_comparisons
from experiments.grid_configurations.grid_pop_share_arrangements import (
    Arrangement,
)
from experiments.grid_configurations.grid_reference_scores import build_grid_reference_scores
from experiments.grid_configurations.plot_grid_score_comparisons import plot_grid_scores
from scipy import sparse


def test_grid_score_comparisons_saves_explicit_categories_and_reference_scores(
    tmp_path, monkeypatch
):
    sample = 0

    def distinct_binary_grid(kind, generator):
        nonlocal sample
        sample += 1
        return np.random.default_rng(sample).permutation(np.repeat([0, 1], 72)).reshape(12, 12)

    monkeypatch.setattr(grid_score_comparisons, "tune_binary_grid", distinct_binary_grid)
    grid_score_comparisons.run_grid_score_comparisons(tmp_path, seed=7)
    scores_df = pd.read_parquet(tmp_path / "grid_scores.parquet")
    assert len(scores_df) == 114
    share_scores_df = scores_df.loc[scores_df.family.eq("shares")]
    assert set(share_scores_df.arrangement) == set(Arrangement)
    assert set(share_scores_df["sample"]) == set(range(1, 7))
    pd.testing.assert_frame_equal(
        pd.read_parquet(tmp_path / "reference_scores.parquet"), build_grid_reference_scores()
    )


def test_binary_grid_scores_draws_exact_score_without_recomputing_on_caller_axes():
    adjacency = sparse.csr_array([[0, 1], [1, 0]])
    scores = calculate_experiment_scores(
        adjacency, np.array([1, 0]), np.array([0, 1]), distinct_people=True
    )
    scores_df = pd.DataFrame(
        [{"family": "binary", "category": "few_unlike", "arrangement": None, **scores.to_record()}]
    )
    original_df = scores_df.copy(deep=True)
    figure, axes = plt.subplots(1, 2)
    try:
        figure_numbers = plt.get_fignums()
        references, categories, arrangements = plot_grid_scores(
            axes[0], scores_df, build_grid_reference_scores(), "capy"
        )
        np.testing.assert_allclose(categories["few_unlike"].get_offsets(), [[0.5, 0]])
        assert all(line in axes[0].lines for line in references)
        assert not arrangements
        assert not axes[1].collections
        assert plt.get_fignums() == figure_numbers
        pd.testing.assert_frame_equal(scores_df, original_df)
    finally:
        plt.close(figure)
