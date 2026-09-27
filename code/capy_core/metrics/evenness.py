"""Dissimilarity, Theil information, and relative diversity from arrays or graph attributes."""

import networkx as nx
import numpy as np
from scipy.special import xlogy

from .errors import UndefinedMetricError, UndefinedMetricReason
from .inputs import (
    WeightMatrix,
    population_shares,
    prepare_weight_matrix,
    node_attribute_to_numpy_arr,
)


def dissimilarity_from_graph(
    graph: nx.Graph,
    group1_attr: str,
    total_attr: str,
    *,
    spatial_weights: WeightMatrix | None = None,
) -> float:
    """Compute dissimilarity from a group's population and its total-population attributes.

    See dissimilarity() for the formula, spatial interpretation, and source.

    Args:
        graph (nx.Graph): Graph with numeric counts. Edges are not read automatically.
        group1_attr (str): Group population attribute.
        total_attr (str): Positive total-population attribute including the group.
        spatial_weights (WeightMatrix | None): Optional local-environment weights in graph node
            order. Default: None, using the units' own shares. Use I+A to include graph neighbors.

    Returns:
        float: Dissimilarity index without modifying the graph or weights.

    Raises:
        KeyError: A population attribute is missing.
        ValueError: Counts or spatial weights are invalid.
        UndefinedMetricError: The group or its complement has zero total population.
    """
    return dissimilarity(
        node_attribute_to_numpy_arr(graph, group1_attr),
        node_attribute_to_numpy_arr(graph, total_attr),
        spatial_weights=spatial_weights,
    )


def dissimilarity(
    group_population: np.ndarray,
    total_population: np.ndarray,
    *,
    spatial_weights: WeightMatrix | None = None,
) -> float:
    r"""
    Calculate dissimilarity from population-weighted deviations in group shares.

    Let $x_i$ be the group population, $t_i$ the total population, $T=\sum_i t_i$, and
    $\rho=\sum_i x_i/T$ the overall group share. The local share is $q_i=x_i/t_i$ by default. With
    spatial weights $W$, use the population share in each weighted local environment:

    $$
    q_i = \frac{(Wx)_i}{(Wt)_i}.
    $$

    The index is

    $$
    D = \frac{\sum_i \frac{t_i}{T}\lvert q_i-\rho\rvert}{2\rho(1-\rho)}.
    $$

    Without spatial weights, this is half the sum of absolute differences between the two groups'
    distributions across units. Smoothing changes local shares but retains $t_i/T$ and $\rho$.

    This is the two-group discrete form of Reardon and O'Sullivan (2004), equation (12), p. 140.
    Their aspatial special case uses each unit as its own environment.
    DOI: https://doi.org/10.1111/j.0081-1750.2004.00150.x.
    The public interface also accepts nonsymmetric $W$, beyond the paper's proximity assumptions.

    Args:
        group_population (np.ndarray): Nonnegative group counts in unit order.
        total_population (np.ndarray): Positive totals including that group, in the same order.
        spatial_weights (WeightMatrix | None): Optional nonnegative local-environment matrix.
            Default: None. Smoothing changes local shares but keeps original population weights.

    Returns:
        float: Dissimilarity index. Neither populations nor weights are changed.

    Raises:
        ValueError: Counts or matrix dimensions/weights are invalid, or an environment is empty.
        UndefinedMetricError: Either comparison group is absent.
    """
    shares, population_weights, overall_share = _prepare_evenness_inputs(
        group_population, total_population, spatial_weights
    )
    return float(
        population_weights
        @ np.abs(shares - overall_share)
        / (2 * overall_share * (1 - overall_share))
    )


def theil_information_from_graph(
    graph: nx.Graph,
    group1_attr: str,
    total_attr: str,
    *,
    spatial_weights: WeightMatrix | None = None,
) -> float:
    """Compute Theil's information index from group and total-population attributes.

    See theil_information() for the formula, spatial interpretation, and source.

    Args:
        graph (nx.Graph): Graph with numeric counts. Edges are not read automatically.
        group1_attr (str): Group population attribute.
        total_attr (str): Positive total-population attribute including the group.
        spatial_weights (WeightMatrix | None): Optional nonnegative local-environment weights in
            graph node order. Default: None, using each unit's own share.

    Returns:
        float: Theil information index; negative spatial values are retained. Inputs are
            unchanged.

    Raises:
        KeyError: A population attribute is missing.
        ValueError: Counts or spatial weights are invalid.
        UndefinedMetricError: The group or its complement is absent.
    """
    return theil_information(
        node_attribute_to_numpy_arr(graph, group1_attr),
        node_attribute_to_numpy_arr(graph, total_attr),
        spatial_weights=spatial_weights,
    )


def theil_information(
    group_population: np.ndarray,
    total_population: np.ndarray,
    *,
    spatial_weights: WeightMatrix | None = None,
) -> float:
    r"""
    Calculate Theil information by comparing local entropy with overall population entropy.

    Let $x_i$ be the group population, $t_i$ the total population, $T=\sum_i t_i$, and
    $\rho=\sum_i x_i/T$ the overall group share. The local share is $q_i=x_i/t_i$ by default. With
    spatial weights $W$, use the population share in each weighted local environment:

    $$
    q_i = \frac{(Wx)_i}{(Wt)_i}.
    $$

    Define binary entropy with the convention $0\log 0=0$. The index is

    $$
    h(q) = -q\log q-(1-q)\log(1-q), \qquad
    H = 1-\frac{\sum_i \frac{t_i}{T}h(q_i)}{h(\rho)}.
    $$

    The score measures the relative reduction in diversity from the whole population to local
    environments. Smoothing retains the original population weights and overall share.

    Reardon and O'Sullivan (2004), equations (6)-(8), p. 139, give the spatial expression and its
    aspatial special case. Replacing their integrals by unit sums gives this implementation. The
    logarithm base cancels in the ratio. DOI: https://doi.org/10.1111/j.0081-1750.2004.00150.x.
    The public interface also accepts nonsymmetric $W$, beyond the paper's proximity assumptions.

    Args:
        group_population (np.ndarray): Nonnegative group counts in unit order.
        total_population (np.ndarray): Positive totals including that group, in the same order.
        spatial_weights (WeightMatrix | None): Optional nonnegative local-environment matrix.
            Default: None. Original population weights and overall share are retained after
            smoothing.

    Returns:
        float: Theil information index without clipping negative spatial values. Inputs are
            unchanged.

    Raises:
        ValueError: Counts or spatial weights are invalid, or an environment has no population.
        UndefinedMetricError: The group or its complement is absent.
    """
    shares, population_weights, overall_share = _prepare_evenness_inputs(
        group_population, total_population, spatial_weights
    )
    overall_entropy = -xlogy(overall_share, overall_share) - xlogy(
        1 - overall_share, 1 - overall_share
    )
    local_entropy = -xlogy(shares, shares) - xlogy(1 - shares, 1 - shares)

    return float(1 - population_weights @ local_entropy / overall_entropy)


def relative_diversity_from_graph(
    graph: nx.Graph,
    group1_attr: str,
    total_attr: str,
    *,
    spatial_weights: WeightMatrix | None = None,
) -> float:
    """Compute relative diversity from group and total-population attributes.

    See relative_diversity() for the formula, spatial interpretation, and source.

    Args:
        graph (nx.Graph): Graph with numeric counts. Edges are not read automatically.
        group1_attr (str): Group population attribute.
        total_attr (str): Positive total-population attribute including the group.
        spatial_weights (WeightMatrix | None): Optional nonnegative local-environment weights in
            graph node order. Default: None, using each unit's own share.

    Returns:
        float: Relative diversity index; negative spatial values are retained. Inputs are
            unchanged.

    Raises:
        KeyError: A population attribute is missing.
        ValueError: Counts or spatial weights are invalid.
        UndefinedMetricError: The group or its complement is absent.
    """
    return relative_diversity(
        node_attribute_to_numpy_arr(graph, group1_attr),
        node_attribute_to_numpy_arr(graph, total_attr),
        spatial_weights=spatial_weights,
    )


def relative_diversity(
    group_population: np.ndarray,
    total_population: np.ndarray,
    *,
    spatial_weights: WeightMatrix | None = None,
) -> float:
    r"""
    Calculate relative diversity by comparing local and overall two-group diversity.

    Let $x_i$ be the group population, $t_i$ the total population, $T=\sum_i t_i$, and
    $\rho=\sum_i x_i/T$ the overall group share. The local share is $q_i=x_i/t_i$ by default. With
    spatial weights $W$, use the population share in each weighted local environment:

    $$
    q_i = \frac{(Wx)_i}{(Wt)_i}.
    $$

    Let $j(q)$ be the probability that two independent population draws have different group
    labels. The index is

    $$
    j(q) = 2q(1-q), \qquad
    R = 1-\frac{\sum_i \frac{t_i}{T}j(q_i)}{j(\rho)}.
    $$

    Smoothing changes the environments being compared but retains the original population weights
    and overall share. This specializes Reardon and O'Sullivan (2004), equations (9)-(11), pp.
    139-140, to two groups and discrete units. The aspatial case uses each unit as its own local
    environment. DOI: https://doi.org/10.1111/j.0081-1750.2004.00150.x. The public interface also
    accepts nonsymmetric $W$, beyond the paper's proximity assumptions.

    Args:
        group_population (np.ndarray): Nonnegative group counts in unit order.
        total_population (np.ndarray): Positive totals including the group, in the same order.
        spatial_weights (WeightMatrix | None): Optional nonnegative local-environment matrix.
            Default: None. Original population weights and overall share are retained after
            smoothing.

    Returns:
        float: Relative diversity index, including negative spatial values. Inputs are unchanged.

    Raises:
        ValueError: Counts or spatial weights are invalid, or an environment has no population.
        UndefinedMetricError: The group or its complement is absent.
    """
    shares, population_weights, overall_share = _prepare_evenness_inputs(
        group_population, total_population, spatial_weights
    )
    overall_diversity = 2 * overall_share * (1 - overall_share)
    local_diversity = 2 * shares * (1 - shares)

    return float(1 - population_weights @ local_diversity / overall_diversity)


def _prepare_evenness_inputs(
    group_population: np.ndarray, total_population: np.ndarray, spatial_weights: WeightMatrix | None
) -> tuple[np.ndarray, np.ndarray, float]:
    """Prepare local shares, original population weights, and overall share for evenness indices.

    Invalid counts/weights or empty environments raise ValueError. An absent group raises
    UndefinedMetricError. Smoothing retains original unit weights; inputs are not modified.
    """
    shares = population_shares(group_population, total_population)
    group_population = np.asarray(group_population, dtype=float)
    total_population = np.asarray(total_population, dtype=float)
    population_weights = total_population / total_population.sum()
    overall_share = float(group_population.sum() / total_population.sum())

    if spatial_weights is not None:
        weights = prepare_weight_matrix(spatial_weights, len(shares))
        neighborhood_population = weights @ total_population

        if np.any(weights.data < 0) or np.any(neighborhood_population <= 0):
            raise ValueError(
                "Local environments require nonnegative weights and positive population"
            )

        shares = (weights @ group_population) / neighborhood_population

    if overall_share == 0 or overall_share == 1:
        raise UndefinedMetricError(UndefinedMetricReason.ABSENT_POPULATION_GROUP)

    return shares, population_weights, overall_share
