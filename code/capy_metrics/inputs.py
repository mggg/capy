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
        np.ndarray: Float array in graph node order. Scalar attributes produce one dimension;
            metric functions check dimensions and validity as demographic data.

    Raises:
        KeyError: A node lacks the requested attribute.
        ValueError: An attribute is complex or cannot be converted to a real number.
        TypeError: An attribute is pd.NA or a nonnumeric object such as a dict.
    """
    return convert_real_values_to_float(
        np.asarray([attributes[attribute] for _, attributes in graph.nodes(data=True)])
    )


def convert_real_values_to_float(values: np.ndarray) -> np.ndarray:
    """Convert real values without silently discarding complex components.

    Missing values may become NaN; callers check finiteness and domain constraints.
    Complex values raise ValueError, including complex scalars inside object arrays.
    Other conversion errors propagate from NumPy. Input arrays are not modified.
    """
    values = np.asarray(values)

    if np.iscomplexobj(values) or (
        values.dtype == object and any(np.iscomplexobj(value) for value in values.flat)
    ):
        raise ValueError("Expected real values, not complex values")

    return np.asarray(values, dtype=float)


def build_csr_adjacency_matrix(graph: nx.Graph) -> sparse.csr_array:
    """Build unweighted binary adjacency in graph node order, ignoring any edge attributes.

    Args:
        graph (nx.Graph): Nonempty undirected simple graph without self-loops. Disconnected
            graphs are accepted. No graph attributes or node identifiers have prescribed names.

    Returns:
        sparse.csr_array: Float adjacency matrix with a zero diagonal.

    Raises:
        ValueError: The graph is empty, directed, a multigraph, or contains self-loops.
    """
    if not graph or graph.is_directed() or graph.is_multigraph() or nx.number_of_selfloops(graph):
        raise ValueError("Expected a nonempty, undirected simple graph without self-loops")

    return nx.to_scipy_sparse_array(
        graph,
        nodelist=list(graph),
        weight=None,  # pyright: ignore[reportArgumentType]
        dtype=float,
        format="csr",
    )


def prepare_population_vectors(
    first_population: np.ndarray, second_population: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Convert two aligned population vectors to floats and reject invalid inputs.

    Args:
        first_population (np.ndarray): Nonempty, one-dimensional nonnegative real population
            data; both counts and fractional estimates are accepted.
        second_population (np.ndarray): Same-length inputs, either another group or a total.
            Fractional estimates are accepted. Functions requiring whole people check that separately.

    Returns:
        tuple[np.ndarray, np.ndarray]: Finite float vectors, possibly sharing input storage.
            Neither input is modified, and callers must not mutate the returned arrays.

    Raises:
        ValueError: Shapes differ, arrays are empty, or values cannot be converted to floats or
            are complex, negative, or nonfinite.
        TypeError: Values are pd.NA or nonnumeric objects such as dicts.
    """
    first_population = convert_real_values_to_float(first_population)
    second_population = convert_real_values_to_float(second_population)

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


def prepare_group_and_total_populations(
    group_population: np.ndarray, total_population: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Prepare float population vectors with positive totals containing the group.

    Args:
        group_population (np.ndarray): Nonnegative group counts or population masses.
        total_population (np.ndarray): Positive totals in the same order, including the group.
            Fractional estimates are accepted for both vectors.

    Returns:
        tuple[np.ndarray, np.ndarray]: Validated group and total vectors, possibly sharing input
            storage. Neither input is modified; callers must not mutate the returned arrays.

    Raises:
        ValueError: Counts are invalid, a total is zero, or a group count exceeds its total.
        TypeError: A population value has an unsupported numeric type, such as pd.NA or a dict.
    """
    group_population, total_population = prepare_population_vectors(
        group_population, total_population
    )

    if np.any(total_population == 0) or np.any(group_population > total_population):
        raise ValueError("Every total must be positive and at least its group population")

    return group_population, total_population


def population_shares(group_population: np.ndarray, total_population: np.ndarray) -> np.ndarray:
    """Divide group populations by positive totals after checking shapes and containment.

    Args:
        group_population (np.ndarray): Nonnegative group counts or population masses.
        total_population (np.ndarray): Positive totals in the same order, including the group.
            Fractional estimates are accepted for both vectors.

    Returns:
        np.ndarray: Finite shares between zero and one.

    Raises:
        ValueError: Counts are invalid, a total is zero, or a group count exceeds its total.
        TypeError: A population value has an unsupported numeric type, such as pd.NA or a dict.
    """
    group_population, total_population = prepare_group_and_total_populations(
        group_population, total_population
    )

    return group_population / total_population


def prepare_weight_matrix(weight_matrix: WeightMatrix, node_count: int) -> sparse.csr_array:
    """Check finite square weights aligned with a known number of population entries.

    Args:
        weight_matrix (WeightMatrix): Dense or CSR spatial weights, including signed weights.
        node_count (int): Required number of rows and columns (the graph's count of nodes).

    Returns:
        sparse.csr_array: Float weights in canonical form (duplicates summed, indices sorted),
            on a copy if the input wasn't already canonical. No input is mutated.

    Raises:
        ValueError: Matrix shape or weight values are invalid.
        TypeError: A weight has an unsupported numeric type, such as pd.NA or a dict.
    """
    if sparse.issparse(weight_matrix):
        if np.iscomplexobj(weight_matrix):
            raise ValueError("Expected real weights, not complex weights")
    else:
        # Convert missing dense entries to NaN before sparse construction can omit them.
        weight_matrix = convert_real_values_to_float(np.asarray(weight_matrix))

    weights = sparse.csr_array(weight_matrix, dtype=float)

    if not weights.has_canonical_format:
        weights = weights.copy()
        weights.sum_duplicates()

    if weights.shape != (node_count, node_count) or not np.isfinite(weights.data).all():
        raise ValueError(
            "Spatial weights must be finite and square, matching the population vectors"
        )

    return weights
