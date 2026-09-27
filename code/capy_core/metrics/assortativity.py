"""Edge and half-edge assortativity after classifying units by their relative group share."""

import networkx as nx
import numpy as np

from .capy import mean_within_group_fraction
from .errors import UndefinedMetricError, UndefinedMetricReason
from .inputs import (
    WeightMatrix,
    build_csr_adjacency_matrix,
    node_attribute_to_numpy_arr,
    population_shares,
    prepare_weight_matrix,
)


def edge_assortativity_from_graph(graph: nx.Graph, group1_attr: str, total_attr: str) -> float:
    """Classify graph units by relative group share and calculate their edge assortativity.

    See edge_assortativity() for the formula and its relationship to categorical assortativity.

    Args:
        graph (nx.Graph): Nonempty undirected simple graph without self-loops; may be disconnected.
        group1_attr (str): Group population attribute.
        total_attr (str): Positive total-population attribute including that group.

    Returns:
        float: Mean same-class edge fraction. Ties at the overall group share enter the first
            class. Classification is temporary; no graph attributes are written.

    Raises:
        KeyError: A population attribute is missing.
        ValueError: Graph structure or population counts are invalid.
        UndefinedMetricError: A class is absent or has no eligible connections.
    """
    return edge_assortativity(
        build_csr_adjacency_matrix(graph),
        node_attribute_to_numpy_arr(graph, group1_attr),
        node_attribute_to_numpy_arr(graph, total_attr),
    )


def edge_assortativity(
    adjacency: WeightMatrix, group_population: np.ndarray, total_population: np.ndarray
) -> float:
    r"""
    Calculate the average same-class edge fraction for each relative-majority class.

    Let $g_i$ and $t_i$ be the group and total populations of unit $i$. Assign the unit to $X$ when
    its local share is at least the overall group share, and to $Y$ otherwise:

    $$
    \frac{g_i}{t_i} \geq \rho, \qquad \rho = \frac{\sum_i g_i}{\sum_i t_i}.
    $$

    Let $a$, $b$, and $c$ denote the undirected edge weights:

    - $a$: edges within $X$.
    - $b$: edges between $X$ and $Y$.
    - $c$: edges within $Y$.

    The score averages the fraction of each class's incident edges that stay within the class,
    counting an internal edge once:

    $$
    S = \frac{1}{2}\left(\frac{a}{a+b} + \frac{c}{c+b}\right).
    $$

    This is a study-specific edge-count convention, not Newman's categorical assortativity.
    See half_edge_assortativity() for the related score that has a Newman correspondence.

    Args:
        adjacency (WeightMatrix): Symmetric nonnegative adjacency with zero diagonal.
        group_population (np.ndarray): Group counts in adjacency order.
        total_population (np.ndarray): Positive totals including that group, in the same order.

    Returns:
        float: Mean same-class edge fraction $S$. A same-class edge contributes once;
            nonbinary adjacency entries act as edge weights. Inputs are unchanged.

    Raises:
        ValueError: Counts or adjacency are invalid.
        UndefinedMetricError: A class is absent or has no eligible connections.
    """
    first_edges, between_edges, second_edges = _relative_majority_edge_totals(
        adjacency, group_population, total_population
    )

    return mean_within_group_fraction(first_edges, between_edges, second_edges)


def half_edge_assortativity_from_graph(graph: nx.Graph, group1_attr: str, total_attr: str) -> float:
    """Compute half-edge assortativity for units classified by their relative group share.

    See half_edge_assortativity() for the formula and its relationship to categorical assortativity.

    Args:
        graph (nx.Graph): Nonempty undirected simple graph without self-loops; may be disconnected.
        group1_attr (str): Group population attribute.
        total_attr (str): Positive total-population attribute including that group.

    Returns:
        float: (1+r)/2 for binary attribute assortativity r on the relative-majority classes.
            Ties at the overall share enter the first class. Graph attributes are unchanged.

    Raises:
        KeyError: A population attribute is missing.
        ValueError: Graph structure or population counts are invalid.
        UndefinedMetricError: A class is absent or has no eligible connections.
    """
    return half_edge_assortativity(
        build_csr_adjacency_matrix(graph),
        node_attribute_to_numpy_arr(graph, group1_attr),
        node_attribute_to_numpy_arr(graph, total_attr),
    )


def half_edge_assortativity(
    adjacency: WeightMatrix, group_population: np.ndarray, total_population: np.ndarray
) -> float:
    r"""
    Calculate the average same-class endpoint fraction for each relative-majority class.

    For group counts $g_i$ and totals $t_i$, assign unit $i$ to $X$ when
    $g_i/t_i \geq \rho$, where $\rho=\sum_i g_i/\sum_i t_i$, and to $Y$ otherwise.
    Let $a$, $b$, and $c$ denote the undirected edge weights:

    - $a$: edges within $X$.
    - $b$: edges between $X$ and $Y$.
    - $c$: edges within $Y$.

    An internal edge supplies two endpoints, so the mean same-class endpoint fraction is

    $$
    S = \frac{1}{2}\left(\frac{2a}{2a+b} + \frac{2c}{2c+b}\right).
    $$

    To relate this to Newman's categorical assortativity, define the binary mixing matrix $E$
    and its row sums $q_i=\sum_j E_{ij}$:

    $$
    E = \frac{1}{2(a+b+c)}\begin{pmatrix}2a & b \\ b & 2c\end{pmatrix},
    \qquad r = \frac{\operatorname{tr}(E)-\sum_i q_i^2}{1-\sum_i q_i^2}.
    $$

    Substitution gives $S=(1+r)/2$. Newman (2003), "Mixing patterns in networks", section II.A,
    equation (2), supplies $r$, while the rescaling and population-share threshold are choices here.
    Source: https://arxiv.org/pdf/cond-mat/0209450 (p. 2).
    DOI: https://doi.org/10.1103/PhysRevE.67.026126.

    Args:
        adjacency (WeightMatrix): Symmetric nonnegative adjacency with zero diagonal.
        group_population (np.ndarray): Group counts in adjacency order.
        total_population (np.ndarray): Positive totals including that group, in the same order.

    Returns:
        float: Mean same-class endpoint fraction $S$. Each same-class edge supplies two endpoints;
            nonbinary adjacency entries act as edge weights. Inputs are unchanged.

    Raises:
        ValueError: Counts or adjacency are invalid.
        UndefinedMetricError: A class is absent or has no eligible connections.
    """
    first_edges, between_edges, second_edges = _relative_majority_edge_totals(
        adjacency, group_population, total_population
    )

    return mean_within_group_fraction(2 * first_edges, between_edges, 2 * second_edges)


def _relative_majority_edge_totals(
    adjacency: WeightMatrix, group_population: np.ndarray, total_population: np.ndarray
) -> tuple[float, float, float]:
    """Check inputs and count first-class, between-class, and second-class edges.

    Invalid counts or adjacency raise ValueError. A missing class raises UndefinedMetricError.
    The first class includes shares equal to the overall share; inputs are never modified.
    """
    group_population = np.asarray(group_population, dtype=float)
    total_population = np.asarray(total_population, dtype=float)
    shares = population_shares(group_population, total_population)
    adjacency = prepare_weight_matrix(adjacency, len(shares))

    if (
        np.any(adjacency.data < 0)
        or np.any(adjacency.diagonal() != 0)
        or (adjacency != adjacency.T).nnz
    ):
        raise ValueError(
            "Assortativity requires symmetric nonnegative adjacency without self-loops"
        )

    overall_share = np.sum(group_population) / np.sum(total_population)
    first_class = (shares >= overall_share).astype(float)
    second_class = 1 - first_class

    if first_class.sum() == 0 or second_class.sum() == 0:
        raise UndefinedMetricError(UndefinedMetricReason.ABSENT_MAJORITY_CLASS)

    first_edges = float(first_class @ (adjacency @ first_class)) / 2
    between_edges = float(first_class @ (adjacency @ second_class))
    second_edges = float(second_class @ (adjacency @ second_class)) / 2

    return first_edges, between_edges, second_edges
