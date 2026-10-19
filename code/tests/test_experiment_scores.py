"""Typed experiment scores and their saved table representation."""

import numpy as np
import pytest
from capy_metrics import UndefinedMetricReason
from experiments.experiment_scores import ExperimentScores, calculate_experiment_scores
from scipy import sparse


def test_experiment_scores_allow_different_metric_selections():
    scores = ExperimentScores(
        group_share=0.5,
        metric_values={"capy": 0.75, "local_exposure": 0.25},
    )

    assert scores.to_record() == {
        "group_share": 0.5,
        "capy": 0.75,
        "capy_undefined_reason": None,
        "local_exposure": 0.25,
        "local_exposure_undefined_reason": None,
    }


@pytest.mark.parametrize(
    "distinct_people, column, expected", [(False, "capy", 0.5), (True, "capy_exact", 0.0)]
)
def test_spatial_capy_keeps_its_formula_name_when_serialized(distinct_people, column, expected):
    adjacency = sparse.csr_array([[0, 1], [1, 0]])
    scores = calculate_experiment_scores(
        adjacency, np.array([1, 0]), np.array([0, 1]), distinct_people=distinct_people
    )
    record = scores.to_record()

    assert scores.metric_values[column] == pytest.approx(expected)
    assert record[column] == pytest.approx(expected)
    assert record[column + "_undefined_reason"] is None
    assert ("capy_exact" if column == "capy" else "capy") not in record


def test_uniform_population_keeps_undefined_moran_distinct_from_zero_dissimilarity():
    adjacency = sparse.csr_array([[0, 1], [1, 0]])
    scores = calculate_experiment_scores(adjacency, np.ones(2), np.ones(2))
    record = scores.to_record()

    assert scores.metric_values["dissimilarity"] == 0
    assert (
        scores.metric_values["moran_row_standardized"] is UndefinedMetricReason.ZERO_SHARE_VARIANCE
    )
    assert record["dissimilarity"] == 0
    assert record["dissimilarity_undefined_reason"] is None
    assert record["moran_row_standardized"] is None
    assert record["moran_row_standardized_undefined_reason"] == "zero_share_variance"
