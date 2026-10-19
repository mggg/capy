"""Hundred-person cells use regular Capy regardless of their binary composition."""

import numpy as np
import pandas as pd
import pytest
from capy_metrics import capy, capy_exact
from experiments.grid_adjacency import build_grid_adjacency
from experiments.grid_configurations import grid_distributions


def test_distribution_scores_use_regular_capy_for_hundred_person_cells(tmp_path, monkeypatch):
    grid = np.tile([0, 1], (10, 5))
    monkeypatch.setattr(grid_distributions, "build_binary_grid", lambda *_: grid)
    grid_distributions.run_grid_distributions(tmp_path, samples=1)
    scores_df = pd.read_parquet(tmp_path / "distribution_scores.parquet")
    adjacency = build_grid_adjacency(10)
    first_population = 100 * grid.ravel()
    expected = capy(adjacency, first_population, 100 - first_population)
    distinct_people = capy_exact(adjacency, first_population, 100 - first_population)

    assert scores_df.capy.tolist() == pytest.approx([expected] * 3)
    assert expected != pytest.approx(distinct_people)
    assert "capy_exact" not in scores_df
