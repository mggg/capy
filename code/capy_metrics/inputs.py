"""Read graph attributes in node order and check the numerical inputs shared by metric families."""

import networkx as nx
import numpy as np
from scipy import sparse

WeightMatrix = sparse.csr_array | sparse.csr_matrix | np.ndarray


def node_attribute_to_numpy_arr(graph: nx.Graph, attribute: str) -> np.ndarray:
    """Read one numeric node attribute in graph iteration order.

    Args:
        graph (nx.Graph): Graph whose node order will also be used for its adjacency matrix.
        attribute (str): Required numeric attribute on every node.

    Returns:
        np.ndarray: One-dimensional float array in graph node order. Metric functions check its meaning.

    Raises:
        KeyError: A node lacks the requested attribute.
        ValueError: An attribute cannot be converted to a number.
    """
    return np.asarray(
        [attributes[attribute] for _, attributes in graph.nodes(data=True)], dtype=float
    )


def build_csr_adjacency_matrix(graph: nx.Graph) -> sparse.csr_array:
    """Build binary adjacency in graph node order, including every edge regardless of attributes.

    Args:
        graph (nx.Graph): Nonempty undirected simple graph without self-loops. Disconnected
            graphs are accepted. No graph attributes or node identifiers have prescribed names.

    Returns:
        sparse.csr_array: Float adjacency with a zero diagonal.

    Raises:
        ValueError: The graph is empty, directed, a multigraph, or contains self-loops.
    """
    if not graph or graph.is_directed() or graph.is_multigraph() or nx.number_of_selfloops(graph):
        raise ValueError("Expected a nonempty, undirected simple graph without self-loops")

    return sparse.csr_array(
        nx.to_scipy_sparse_array(graph, nodelist=list(graph), weight=None, dtype=float)  # pyright: ignore[reportArgumentType]
    )


def prepare_population_vectors(
    first_population: np.ndarray, second_population: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Convert two aligned population vectors to floats and reject invalid counts.

    Args:
        first_population (np.ndarray): Nonempty, one-dimensional nonnegative counts.
        second_population (np.ndarray): Same-length counts, either another group or a total.
            Fractional estimates are accepted. Functions requiring whole people check that separately.

    Returns:
        tuple[np.ndarray, np.ndarray]: Finite float vectors, possibly sharing input storage.
            Neither input is modified, and callers must not mutate the returned arrays.

    Raises:
        ValueError: Shapes differ, arrays are empty, or counts are negative or nonfinite.
    """
    first_population = np.asarray(first_population, dtype=float)
    second_population = np.asarray(second_population, dtype=float)

    if (
        first_population.ndim != 1
        or first_population.size == 0
        or second_population.shape != first_population.shape
    ):
        raise ValueError("Populations must be aligned, nonempty one-dimensional vectors")

    if (
        not np.isfinite(first_population).all()
        or not np.isfinite(second_population).all()
        or np.any(first_population < 0)
        or np.any(second_population < 0)
    ):
        raise ValueError(
            "Populations must be aligned, nonempty vectors of finite nonnegative counts"
        )

    return first_population, second_population


def population_shares(group_population: np.ndarray, total_population: np.ndarray) -> np.ndarray:
    """Divide group counts by positive totals after checking their shapes and containment.

    Args:
        group_population (np.ndarray): Nonnegative group counts.
        total_population (np.ndarray): Positive totals in the same order, including the group.

    Returns:
        np.ndarray: Finite shares between zero and one.

    Raises:
        ValueError: Counts are invalid, a total is zero, or a group count exceeds its total.
    """
    group_population, total_population = prepare_population_vectors(
        group_population, total_population
    )

    if np.any(total_population == 0) or np.any(group_population > total_population):
        raise ValueError("Every total must be positive and at least its group population")

    return group_population / total_population


def prepare_weight_matrix(weight_matrix: WeightMatrix, node_count: int) -> sparse.csr_array:
    """Check finite square weights aligned with a known number of population entries.

    Args:
        weight_matrix (WeightMatrix): Dense or CSR spatial weights, including signed weights.
        node_count (int): Required number of rows and columns.

    Returns:
        sparse.csr_array: Float weights with duplicate entries combined on a private copy when needed.
            Already canonical inputs may share storage; no input is mutated.

    Raises:
        ValueError: Matrix shape or weight values are invalid.
    """
    weights = sparse.csr_array(weight_matrix, dtype=float)

    if not weights.has_canonical_format:
        weights = weights.copy()
        weights.sum_duplicates()

    if weights.shape != (node_count, node_count) or not np.isfinite(weights.data).all():
        raise ValueError(
            "Spatial weights must be finite and square, matching the population vectors"
        )

    return weights
