"""Shared score selection for synthetic and observed dispersion experiments."""

import numpy as np
from capy_metrics import (
    MoranWeightType,
    UndefinedMetricError,
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


def calculate_example_scores(
    adjacency: sparse.csr_array,
    first_population: np.ndarray,
    second_population: np.ndarray,
    *,
    distinct_people: bool = False,
) -> dict[str, float | str | None]:
    """Calculate the comparison scores and two Moran conventions on aligned populations.

    Args:
        adjacency (sparse.csr_array): Symmetric binary adjacency without self-loops, aligned with
            the population arrays.
        first_population (np.ndarray): First-group counts or continuous masses, in node order.
        second_population (np.ndarray): Second-group counts or masses in the same order.
        distinct_people (bool): Use exact spatial Capy for integer people, default False. Aspatial
            Capy remains quadratic, matching the national score convention.

    Returns:
        dict[str, float | str | None]: Values, group share, and a reason column for each undefined
            score. Population totals must be positive at every unit.

    Raises:
        ValueError: Populations or adjacency are invalid, or exact Capy receives noninteger
            counts.
    """
    totals = first_population + second_population
    closed_adjacency = adjacency + sparse.eye_array(len(totals), format="csr")
    scores: dict[str, float | str | None] = {
        "group_share": float(first_population.sum() / totals.sum())
    }

    for metric_name, operation in (
        ("dissimilarity", dissimilarity),
        ("entropy_index", entropy_index),
        ("relative_diversity", relative_diversity),
    ):
        for prefix, weights in (("", None), ("spatial_", closed_adjacency)):
            name = prefix + metric_name
            try:
                scores[name] = operation(first_population, totals, spatial_weights=weights)
                scores[name + "_undefined_reason"] = None
            except UndefinedMetricError as error:
                scores[name] = None
                scores[name + "_undefined_reason"] = error.reason.value

    for name in ("aspatial_capy", "capy_exact" if distinct_people else "capy"):
        try:
            if name == "aspatial_capy":
                scores[name] = aspatial_capy(first_population, second_population)
            elif distinct_people:
                scores[name] = capy_exact(adjacency, first_population, second_population)
            else:
                scores[name] = capy(adjacency, first_population, second_population)

            scores[name + "_undefined_reason"] = None
        except UndefinedMetricError as error:
            scores[name] = None
            scores[name + "_undefined_reason"] = error.reason.value

    for weight_type in (MoranWeightType.WITH_SELF, MoranWeightType.ROW_STANDARDIZED):
        name = f"moran_{weight_type}"
        try:
            weights = build_moran_weights(adjacency, weight_type)
            scores[name] = morans_I(weights, first_population / totals)
            scores[name + "_undefined_reason"] = None
        except UndefinedMetricError as error:
            scores[name] = None
            scores[name + "_undefined_reason"] = error.reason.value

    return scores
