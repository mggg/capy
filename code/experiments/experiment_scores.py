"""Shared score selection for synthetic and observed dispersion experiments."""

from dataclasses import dataclass

import numpy as np
from capy_metrics import (
    MoranWeightType,
    UndefinedMetricError,
    UndefinedMetricReason,
    aspatial_capy,
    build_moran_weights,
    capy,
    capy_exact,
    dissimilarity,
    entropy_index,
    morans_I,
    relative_diversity,
)
from scipy import sparse

ScoreValue = float | UndefinedMetricReason


@dataclass(frozen=True)
class ExperimentScores:
    """Named scores and first-group population share for one arrangement.

    Metric values contain either a number or the reason a score is undefined. Each name
    identifies its formula, such as "capy" or "capy_exact"; experiments may use different
    collections of metrics.
    """

    group_share: float
    metric_values: dict[str, ScoreValue]

    def to_record(self) -> dict[str, float | str | None]:
        """Flatten scores into table columns with paired undefined-reason columns."""
        record: dict[str, float | str | None] = {"group_share": self.group_share}

        for name, value in self.metric_values.items():
            if isinstance(value, UndefinedMetricReason):
                record[name] = None
                record[name + "_undefined_reason"] = value.value
            else:
                record[name] = value
                record[name + "_undefined_reason"] = None

        return record


def calculate_experiment_scores(
    adjacency: sparse.csr_array,
    first_population: np.ndarray,
    second_population: np.ndarray,
    *,
    distinct_people: bool = False,
) -> ExperimentScores:
    """Calculate the comparison scores and two Moran conventions on aligned populations.

    Args:
        adjacency (sparse.csr_array): Symmetric binary adjacency without self-loops, aligned with
            the population arrays.
        first_population (np.ndarray): First-group counts or continuous masses, in node order.
        second_population (np.ndarray): Second-group counts or masses in the same order.
        distinct_people (bool): Use exact spatial Capy for integer people, default False. Aspatial
            Capy remains quadratic, matching the national score convention.

    Returns:
        ExperimentScores: Group share and scores, with reasons for undefined values. Population
            totals must be positive at every unit.

    Raises:
        ValueError: Populations or adjacency are invalid, or exact Capy receives noninteger
            counts.
    """
    totals = first_population + second_population
    closed_adjacency = adjacency + sparse.eye_array(len(totals), format="csr")
    scores: dict[str, ScoreValue] = {}
    capy_name = "capy_exact" if distinct_people else "capy"

    for metric_name, operation in (
        ("dissimilarity", dissimilarity),
        ("entropy_index", entropy_index),
        ("relative_diversity", relative_diversity),
    ):
        for prefix, weights in (("", None), ("spatial_", closed_adjacency)):
            name = prefix + metric_name
            try:
                scores[name] = operation(first_population, totals, spatial_weights=weights)
            except UndefinedMetricError as error:
                scores[name] = error.reason

    for name in ("aspatial_capy", capy_name):
        try:
            if name == "aspatial_capy":
                scores[name] = aspatial_capy(first_population, second_population)
            elif distinct_people:
                scores[name] = capy_exact(adjacency, first_population, second_population)
            else:
                scores[name] = capy(adjacency, first_population, second_population)

        except UndefinedMetricError as error:
            scores[name] = error.reason

    for weight_type in (MoranWeightType.WITH_SELF, MoranWeightType.ROW_STANDARDIZED):
        name = f"moran_{weight_type}"
        try:
            weights = build_moran_weights(adjacency, weight_type)
            scores[name] = morans_I(weights, first_population / totals)
        except UndefinedMetricError as error:
            scores[name] = error.reason

    return ExperimentScores(
        group_share=float(first_population.sum() / totals.sum()),
        metric_values=scores,
    )
