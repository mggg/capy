"""Capy scores with explicit neighbor weights and self-pairing conventions."""

import networkx as nx
import numpy as np
from scipy import sparse

from .errors import UndefinedMetricError, UndefinedMetricReason
from .inputs import (
    WeightMatrix,
    build_csr_adjacency_matrix,
    node_attribute_to_numpy_arr,
    prepare_population_vectors,
    prepare_weight_matrix,
)


def mean_within_group_fraction(
    first_group_pairs: float,
    between_group_pairs: float,
    second_group_pairs: float,
) -> float:
    r"""Average the fraction of interactions staying within each group.

    For within-group totals $a,c$ and between-group total $b$, return

    $$
    \frac{1}{2}\left(\frac{a}{a+b}+\frac{c}{c+b}\right).
    $$

    Callers determine which interactions count and supply their weights consistently.

    Args:
        first_group_pairs (float): Interaction weight within the first group.
        between_group_pairs (float): Interaction weight between the groups.
        second_group_pairs (float): Interaction weight within the second group.

    Returns:
        float: Equally weighted mean of the two within-group fractions.

    Raises:
        ValueError: Interaction totals are negative or nonfinite.
        UndefinedMetricError: Either group has no eligible interactions.
    """
    pair_totals = np.asarray([first_group_pairs, between_group_pairs, second_group_pairs])

    if not np.isfinite(pair_totals).all() or np.any(pair_totals < 0):
        raise ValueError("Pair totals must be finite and nonnegative")

    first_group_total = first_group_pairs + between_group_pairs
    second_group_total = second_group_pairs + between_group_pairs

    if first_group_total == 0 or second_group_total == 0:
        raise UndefinedMetricError(UndefinedMetricReason.NO_PAIR_INTERACTIONS)

    return 0.5 * (first_group_pairs / first_group_total + second_group_pairs / second_group_total)


def aspatial_capy_from_graph(graph: nx.Graph, group1_attr: str, group2_attr: str) -> float:
    """Compute quadratic within-unit Capy from two disjoint population attributes.

    See aspatial_capy() for the formula and interaction-counting convention.

    Args:
        graph (nx.Graph): Graph with nonnegative population attributes. Edges are not used.
        group1_attr (str): First group's population attribute.
        group2_attr (str): Second group's population attribute, not the total population.

    Returns:
        float: Aspatial Capy score, including self-pairs. Graph attributes are unchanged.

    Raises:
        KeyError: A population attribute is missing.
        ValueError: Population vectors are empty, negative, or nonfinite.
        UndefinedMetricError: A group has no eligible pair interactions.
    """
    return aspatial_capy(
        node_attribute_to_numpy_arr(graph, group1_attr),
        node_attribute_to_numpy_arr(graph, group2_attr),
    )


def aspatial_capy(first_population: np.ndarray, second_population: np.ndarray) -> float:
    r"""
    Calculate aspatial Capy, $C_0$ from within-unit inner products, including self-pairs.

    Let $x$ and $y$ be the population vectors for two disjoint groups. Within-unit interaction
    totals use the ordinary inner product $\langle u,v\rangle=\sum_i u_i v_i$:

    $$
    a=\langle x,x\rangle, \qquad b=\langle x,y\rangle, \qquad c=\langle y,y\rangle.
    $$

    Capy is the mean of the two groups' same-group interaction fractions:

    $$
    C_0 = \frac{1}{2}\left(\frac{a}{a+b}+\frac{c}{c+b}\right).
    $$

    This is $C_0$, the quadratic score at zero neighbor weight. It includes each person's
    interaction with themselves, so it can differ from capy_exact() even when both ignore
    neighbors.

    Args:
        first_population (np.ndarray): Nonnegative counts for the first group.
        second_population (np.ndarray): Same-length counts for the second, disjoint group.
            Fractional estimates are accepted, and zero-population units contribute nothing.

    Returns:
        float: Mean of the two group skews with identity weights. Neither input is changed.

    Raises:
        ValueError: Counts are invalid or vector shapes disagree.
        UndefinedMetricError: Either group's skew has zero denominator.
    """
    first_population, second_population = prepare_population_vectors(
        first_population, second_population
    )
    first_group_inner_product = float(first_population @ first_population)
    between_group_inner_product = float(first_population @ second_population)
    second_group_inner_product = float(second_population @ second_population)

    return mean_within_group_fraction(
        first_group_inner_product, between_group_inner_product, second_group_inner_product
    )


def capy_from_graph(graph: nx.Graph, group1_attr: str, group2_attr: str, lam: float = 1) -> float:
    """Compute quadratic Capy with neighbor weight lam, retaining within-unit self-pairs.

    See capy() for the formula and interaction-counting convention.

    Args:
        graph (nx.Graph): Nonempty undirected simple graph without self-loops; may be
            disconnected.
        group1_attr (str): First group's nonnegative population attribute.
        group2_attr (str): Second, disjoint group's population attribute.
        lam (float): Finite nonnegative neighbor multiplier. Within-unit weight stays one.
            Default: 1.

    Returns:
        float: Capy score. Zero weight gives aspatial_capy(); inputs are unchanged.

    Raises:
        KeyError: A population attribute is missing.
        ValueError: Graph structure, counts, or lam are invalid.
        UndefinedMetricError: A group's skew has zero denominator.
    """
    return capy(
        build_csr_adjacency_matrix(graph),
        node_attribute_to_numpy_arr(graph, group1_attr),
        node_attribute_to_numpy_arr(graph, group2_attr),
        lam,
    )


def capy(
    adjacency: WeightMatrix,
    first_population: np.ndarray,
    second_population: np.ndarray,
    lam: float = 1,
) -> float:
    r"""
    Calculate Capy with parameterized neighbor weights, including self-pairs.

    Let $x$ and $y$ be the population vectors for two disjoint groups, $A$ the neighbor-weight
    matrix, and $\lambda=\text{lam}\geq0$. Write $\langle u,v\rangle_W=\langle u,Wv\rangle$, where
    $\langle u,v\rangle=\sum_i u_i v_i$. Within-unit weight stays one:

    $$ W_\lambda=I+\lambda A, \qquad \begin{aligned}
    a &= \langle x,x\rangle_{W_\lambda}, \\
    b &= \langle x,y\rangle_{W_\lambda}, \\
    c &= \langle y,y\rangle_{W_\lambda}. \end{aligned} $$

    Capy is the mean of the two groups' same-group interaction fractions:

    $$
    C = \frac{1}{2}\left(\frac{a}{a+b}+\frac{c}{c+b}\right).
    $$

    These quadratic totals include self-pairs. Setting $\lambda=0$ gives aspatial_capy(); setting
    $\lambda=1$ gives equal within-unit and neighbor multipliers. Use capy_exact() to exclude
    self-pairs when the populations are integer counts.

    Notes:
        This quadratic formulation has three useful mathematical properties that make it
        convenient when examining population distributions compared to the `capy_exact()` formula:

        - Population-scale invariance: replacing $x,y$ by $s x,s y$ for any $s>0$ leaves the score
          unchanged, since all three interaction totals scale by $s^2$. The adjacency and
          $\lambda$ remain fixed.
        - Common-composition baseline: if every populated unit has the same group share
          $p\in(0,1)$, the two same-group fractions are $p$ and $1-p$, giving $C=1/2$.
        - Continuous populations: the formula accepts nonnegative fractional counts or population
          masses and is continuous wherever both denominators are positive.

        These properties concern the mathematical formula; floating-point evaluation is subject to
        rounding and overflow. The distinct-person correction in capy_exact() introduces
        population-size dependence and need not preserve the $1/2$ baseline. "Exact" refers to
        counting distinct people, not to a universally more accurate score.

    Args:
        adjacency (WeightMatrix): Symmetric nonnegative neighbor weights with zero diagonal.
        first_population (np.ndarray): First group's nonnegative counts in adjacency order.
        second_population (np.ndarray): Counts for the second, disjoint group in the same order.
        lam (float): Finite nonnegative multiplier of neighbor interactions. Within-unit weight
            stays one. Default: 1; zero gives the aspatial score. Infinite weights are not
            accepted.

    Returns:
        float: Mean of the two group skews, including self-pairs. Inputs are unchanged.

    Raises:
        ValueError: Counts, adjacency, or lam are invalid.
        UndefinedMetricError: A group's skew has zero denominator.
    """
    first_population, second_population = prepare_population_vectors(
        first_population, second_population
    )
    adjacency = _prepare_capy_adjacency(adjacency, len(first_population), lam)
    first_inner_product = float(
        first_population @ first_population
        + lam * (first_population @ (adjacency @ first_population))
    )
    between_inner_product = float(
        first_population @ second_population
        + lam * (first_population @ (adjacency @ second_population))
    )
    second_inner_product = float(
        second_population @ second_population
        + lam * (second_population @ (adjacency @ second_population))
    )

    return mean_within_group_fraction(
        first_inner_product, between_inner_product, second_inner_product
    )


def capy_exact_from_graph(
    graph: nx.Graph, group1_attr: str, group2_attr: str, lam: float = 1
) -> float:
    """Compute distinct-person Capy with neighbor weight lam and no self-pairs.

    See capy_exact() for the formula and interaction-counting convention.

    Args:
        graph (nx.Graph): Nonempty undirected simple graph without self-loops; may be
            disconnected.
        group1_attr (str): First group's nonnegative integer population attribute.
        group2_attr (str): Second, disjoint group's nonnegative integer population attribute.
        lam (float): Finite nonnegative neighbor multiplier. Within-unit weight stays one.
            Default: 1.

    Returns:
        float: Exact Capy score. At zero neighbor weight, self-pairs are still excluded; this
            differs from aspatial_capy(). The input graph is unchanged.

    Raises:
        KeyError: A population attribute is missing.
        ValueError: Graph structure, integer counts, or lam are invalid.
        UndefinedMetricError: A group's skew has zero denominator.
    """
    return capy_exact(
        build_csr_adjacency_matrix(graph),
        node_attribute_to_numpy_arr(graph, group1_attr),
        node_attribute_to_numpy_arr(graph, group2_attr),
        lam,
    )


def capy_exact(
    adjacency: WeightMatrix,
    first_population: np.ndarray,
    second_population: np.ndarray,
    lam: float = 1,
) -> float:
    r"""
    Calculate Capy from distinct-person interactions with parameterized neighbor weights.

    Let $x$ and $y$ be integer population vectors for two disjoint groups, $A$ the neighbor-weight
    matrix, and $\lambda=\text{lam}\geq0$. Write $\langle u,v\rangle=\sum_i u_i v_i$ and
    $\langle u,v\rangle_A=\langle u,Av\rangle$. The interaction totals exclude self-pairs:

    $$ \begin{aligned}
    a &= \sum_i x_i(x_i-1)+\lambda \langle x,x\rangle_A, \\
    b &= \langle x,y\rangle+\lambda \langle x,y\rangle_A, \\
    c &= \sum_i y_i(y_i-1)+\lambda \langle y,y\rangle_A. \end{aligned} $$

    Capy is the mean of the two groups' same-group interaction fractions:

    $$
    C = \frac{1}{2}\left(\frac{a}{a+b}+\frac{c}{c+b}\right).
    $$

    Same-group totals count ordered pairs of distinct people. Between-group pairs need no
    self-pair correction. At $\lambda=0$, only within-unit interactions remain, but the result can
    differ from aspatial_capy(), which includes self-pairs.

    Args:
        adjacency (WeightMatrix): Symmetric nonnegative neighbor weights with zero diagonal.
        first_population (np.ndarray): First group's nonnegative integer counts in adjacency
            order.
        second_population (np.ndarray): Second, disjoint group's integer counts in the same order.
        lam (float): Finite nonnegative neighbor multiplier. Within-unit weight stays one.
            Default: 1. At zero, only distinct-person within-unit interactions remain.

    Returns:
        float: Mean of X-skew and Y-skew. The same-group terms subtract each group's population to
            exclude self-pairs; the between-group inner product is unchanged. Inputs are
            unchanged.

    Raises:
        ValueError: Counts, adjacency, or lam are invalid, including fractional counts.
        UndefinedMetricError: A group's skew has zero denominator.
    """
    first_population, second_population = prepare_population_vectors(
        first_population, second_population
    )

    if np.any(first_population != np.floor(first_population)) or np.any(
        second_population != np.floor(second_population)
    ):
        raise ValueError("Distinct-person Capy scores require integer population counts")

    adjacency = _prepare_capy_adjacency(adjacency, len(first_population), lam)
    first_group_distinct_pairs = float(
        first_population @ (first_population - 1)
        + lam * (first_population @ (adjacency @ first_population))
    )
    between_inner_product = float(
        first_population @ second_population
        + lam * (first_population @ (adjacency @ second_population))
    )
    second_group_distinct_pairs = float(
        second_population @ (second_population - 1)
        + lam * (second_population @ (adjacency @ second_population))
    )

    return mean_within_group_fraction(
        first_group_distinct_pairs, between_inner_product, second_group_distinct_pairs
    )


def _prepare_capy_adjacency(
    adjacency: WeightMatrix, node_count: int, lam: float
) -> sparse.csr_array:
    """Check symmetric neighbor weights and a finite nonnegative lambda without changing inputs.

    Args:
        adjacency (WeightMatrix): Neighbor weights; self-pairs are handled by the score formula.
        node_count (int): Required row and column count, matching both population vectors.
        lam (float): Neighbor-interaction multiplier in I + lam*A.

    Returns:
        sparse.csr_array: Finite nonnegative symmetric weights with zero diagonal.

    Raises:
        ValueError: Weights are invalid or lam is not finite and nonnegative.
    """
    adjacency = prepare_weight_matrix(adjacency, node_count)

    if (
        np.any(adjacency.data < 0)
        or np.any(adjacency.diagonal() != 0)
        or (adjacency != adjacency.T).nnz
    ):
        raise ValueError("Capy adjacency must be symmetric, nonnegative, and zero-diagonal")

    if not np.isfinite(lam) or lam < 0:
        raise ValueError("Neighbor weight lam must be finite and nonnegative")

    return adjacency
