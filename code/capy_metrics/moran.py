"""Moran's I from numerical inputs or graph attributes, with explicit spatial-weight conventions."""

from enum import StrEnum

import networkx as nx
import numpy as np
from scipy import sparse
from scipy.spatial.distance import cdist

from .errors import UndefinedMetricError, UndefinedMetricReason
from .inputs import (
    WeightMatrix,
    build_csr_adjacency_matrix,
    node_attribute_to_numpy_arr,
    population_shares,
    prepare_weight_matrix,
)


class MoranWeightType(StrEnum):
    """Spatial weights for Moran scores, with all distance rows standardized to sum to one.

    ADJACENCY is binary A; WITH_SELF is I+A; ROW_STANDARDIZED divides A's rows by degree.
    NEGATIVE_LAPLACIAN is A-diag(degree), with absolute-weight normalization in morans_I().
    METROPOLIS uses 1/max(degree_i, degree_j) on edges and fills each diagonal to row sum one.
    INVERSE_DISTANCE and INVERSE_SQUARED_DISTANCE row-standardize 1/d and 1/d² respectively,
    using projected centroid coordinates and zero self-weights.
    """

    ADJACENCY = "adjacency"
    WITH_SELF = "with_self"
    ROW_STANDARDIZED = "row_standardized"
    NEGATIVE_LAPLACIAN = "negative_laplacian"
    METROPOLIS = "metropolis"
    INVERSE_DISTANCE = "inverse_distance"
    INVERSE_SQUARED_DISTANCE = "inverse_squared_distance"


DISTANCE_WEIGHT_POWERS = {
    MoranWeightType.INVERSE_DISTANCE: 1,
    MoranWeightType.INVERSE_SQUARED_DISTANCE: 2,
}


def morans_I_from_graph(
    graph: nx.Graph,
    group1_attr: str,
    total_attr: str,
    weight_type: MoranWeightType = MoranWeightType.ROW_STANDARDIZED,
    *,
    centroid_attributes: tuple[str, str] = ("centroid_x", "centroid_y"),
) -> float:
    """Compute one Moran score from group shares and the selected graph weights.

    See morans_I() for the statistic and citation, and MoranWeightType for each weight matrix.
    Distance choices use the same formula through distance_morans_I().

    Args:
        graph (nx.Graph): Graph with numeric population attributes. Adjacency weights require an
            undirected simple graph without self-loops; connectedness is not required.
        group1_attr (str): Attribute containing the group's population at each node.
        total_attr (str): Attribute containing positive totals that include that group.
        weight_type (MoranWeightType): Spatial weights, defaulting to row-standardized adjacency.
        centroid_attributes (tuple[str, str]): X/Y attributes for distance weights. Coordinates
            must share a projected coordinate system. Default: centroid_x and centroid_y.

    Returns:
        float: The requested Moran score.

    Raises:
        KeyError: A required population or coordinate attribute is missing.
        ValueError: Counts, graph structure, weights, or coordinates are invalid.
        UndefinedMetricError: Shares are constant, weights have no neighbors, or centroids coincide.
    """
    shares = population_shares(
        node_attribute_to_numpy_arr(graph, group1_attr),
        node_attribute_to_numpy_arr(graph, total_attr),
    )
    weight_type = MoranWeightType(weight_type)

    if weight_type in DISTANCE_WEIGHT_POWERS:
        coordinates = np.column_stack(
            [node_attribute_to_numpy_arr(graph, attribute) for attribute in centroid_attributes]
        )
        return distance_morans_I(coordinates, shares, DISTANCE_WEIGHT_POWERS[weight_type])

    adjacency = build_csr_adjacency_matrix(graph)
    weights = build_moran_weights(adjacency, weight_type)

    return morans_I(weights, shares)


def morans_I(weight_matrix: WeightMatrix, population_shares: np.ndarray) -> float:
    r"""
    Calculate Moran's I from aligned spatial weights and population shares.

    Let $p_i$ be the share at unit $i$, $n$ the number of units, and $W$ the supplied weight matrix.
    Center shares using their unweighted mean:

    $$
    \bar p = \frac{1}{n}\sum_i p_i, \qquad z_i=p_i-\bar p.
    $$

    Write $\langle u,v\rangle=\sum_i u_i v_i$ and $\langle u,v\rangle_W=\langle u,Wv\rangle$.
    The score compares association between linked deviations with the variation in those shares:

    $$
    I_W = \frac{n}{\sum_{i,j}\lvert W_{ij}\rvert}
          \frac{\langle z,z\rangle_W}{\langle z,z\rangle}.
    $$

    For nonnegative weights, the denominator is the usual sum of weights. This matches Luc
    Anselin's GeoDa workbook (2020), "Global Spatial Autocorrelation (1)", Concept / Moran's I:
    https://geodacenter.github.io/workbook/5a_global_auto/lab5a.html#morans-i.

    Absolute-weight normalization for signed matrices is a separate convention here. In particular,
    $W=A-\operatorname{diag}(d)$ has signed sum zero, where $d$ is the vector of node degrees.
    Its score is therefore not the ordinary Moran statistic in that reference.

    Args:
        weight_matrix (WeightMatrix): Finite dense or CSR weights in share-vector order. Weights
            are used as supplied, without row standardization. Signed weights use absolute-sum
            normalization, including the negative Laplacian whose signed sum is zero.
        population_shares (np.ndarray): Nonempty one-dimensional shares between zero and one.
            Centering uses their unweighted mean, not the overall population-weighted share.

    Returns:
        float: Unclipped Moran score.

    Raises:
        ValueError: Shares or weights are invalid or their dimensions disagree.
        UndefinedMetricError: Shares are constant or the weights have zero total absolute mass.
    """
    shares = _check_shares(population_shares)
    weights = prepare_weight_matrix(weight_matrix, len(shares))
    centered_shares = _center_varying_shares(shares)
    total_weight = float(abs(weights).sum())

    if total_weight == 0:
        raise UndefinedMetricError(UndefinedMetricReason.NO_NEIGHBORS)

    return float(
        len(shares)
        / total_weight
        * (centered_shares @ (weights @ centered_shares))
        / (centered_shares @ centered_shares)
    )


def build_moran_weights(adjacency: WeightMatrix, weight_type: MoranWeightType) -> sparse.csr_array:
    r"""
    Build one adjacency-based weight matrix for reuse across population comparisons.

    Let $A$ be binary adjacency, $d_i=\sum_j A_{ij}$ node degree, and $I$ the identity matrix.
    MoranWeightType selects one of these matrices:

    - ADJACENCY: $W=A$.
    - WITH_SELF: $W=I+A$.
    - ROW_STANDARDIZED: $W_{ij}=A_{ij}/d_i$, with zero rows for isolated nodes.
    - NEGATIVE_LAPLACIAN: $W=A-\operatorname{diag}(d)$.
    - METROPOLIS: for adjacent, distinct nodes, use

    $$
    W_{ij}=\frac{1}{\max(d_i,d_j)}, \qquad W_{ii}=1-\sum_{j\ne i}W_{ij}.
    $$

    All other off-diagonal Metropolis weights are zero. This matrix appears in Xiao and Boyd
    (2004), section 4.2, p. 70, and equation (18), p. 69:
    https://web.stanford.edu/~boyd/papers/pdf/fastavg.pdf. That paper supplies the averaging
    matrix; applying morans_I() to it is a choice made here.

    Args:
        adjacency (WeightMatrix): Symmetric binary adjacency with zero diagonal.
        weight_type (MoranWeightType): One of the five adjacency conventions. Distance weights
            are evaluated with distance_morans_I() so a full pairwise matrix is unnecessary.

    Returns:
        sparse.csr_array: Requested weights. Row-standardized adjacency leaves isolated rows zero.

    Raises:
        ValueError: Adjacency is invalid or a distance-weight type is requested.
    """
    adjacency = sparse.csr_array(adjacency, dtype=float)
    if adjacency.shape is None or len(adjacency.shape) != 2:
        raise ValueError("Adjacency must be a two-dimensional matrix")

    adjacency = prepare_weight_matrix(adjacency, adjacency.shape[0])

    if (
        np.any((adjacency.data != 0) & (adjacency.data != 1))
        or np.any(adjacency.diagonal() != 0)
        or (adjacency != adjacency.T).nnz
    ):
        raise ValueError(
            "Moran graph weights require symmetric binary adjacency without self-loops"
        )

    weight_type = MoranWeightType(weight_type)
    degrees = np.asarray(adjacency.sum(axis=1)).ravel()

    if weight_type == MoranWeightType.ADJACENCY:
        return adjacency.copy()

    if weight_type == MoranWeightType.WITH_SELF:
        return adjacency + sparse.eye_array(len(degrees), format="csr")

    if weight_type == MoranWeightType.ROW_STANDARDIZED:
        inverse_degrees = np.divide(1.0, degrees, out=np.zeros_like(degrees), where=degrees > 0)
        return sparse.csr_array(sparse.diags_array(inverse_degrees) @ adjacency)

    if weight_type == MoranWeightType.NEGATIVE_LAPLACIAN:
        return adjacency - sparse.diags_array(degrees)

    if weight_type == MoranWeightType.METROPOLIS:
        edges = adjacency.tocoo()
        nonzero = edges.data != 0
        rows, columns = edges.row[nonzero], edges.col[nonzero]
        edge_weights = 1 / np.maximum(degrees[rows], degrees[columns])
        weights = sparse.csr_array((edge_weights, (rows, columns)), shape=adjacency.shape)
        diagonal = 1 - np.asarray(weights.sum(axis=1)).ravel()
        return weights + sparse.diags_array(diagonal)

    raise ValueError("Use distance_morans_I() for distance-based weights")


def distance_morans_I(
    centroid_coordinates: np.ndarray, population_shares: np.ndarray, distance_power: float = 1
) -> float:
    r"""
    Calculate Moran's I with row-standardized inverse-distance weights in bounded batches.

    Let $d_{ij}$ be the Euclidean distance between centroids $i$ and $j$, and let
    $\alpha=\text{distance\_power}>0$. The weights are

    $$
    W_{ij} = \frac{d_{ij}^{-\alpha}}{\sum_{k\ne i} d_{ik}^{-\alpha}} \quad (i\ne j),
    \qquad W_{ii}=0.
    $$

    With $z_i=p_i-\bar p$ for population shares $p_i$ and their unweighted mean $\bar p$, the score
    simplifies because every row sums to one. Using $\langle u,v\rangle=\sum_i u_i v_i$ and
    $\langle u,v\rangle_W=\langle u,Wv\rangle$ gives

    $$
    I_W = \frac{\langle z,z\rangle_W}{\langle z,z\rangle}.
    $$

    See morans_I() for the statistic's source. All-pairs distances, their exponent, and row
    standardization are weight choices here, rather than a separate score from that reference.

    Args:
        centroid_coordinates (np.ndarray): Finite projected coordinates in share order, shape (n, 2).
        population_shares (np.ndarray): Nonempty one-dimensional shares between zero and one.
        distance_power (float): Positive finite exponent in 1/distance**power. Default: 1.
            Use 2 for inverse-squared distance. Self-weights are zero.

    Returns:
        float: Exact all-pairs score without storing the full distance matrix.

    Raises:
        ValueError: Shares, coordinate dimensions, or the distance exponent are invalid.
        UndefinedMetricError: Shares are constant or two distinct nodes have coincident centroids.
    """
    shares = _check_shares(population_shares)
    coordinates = np.asarray(centroid_coordinates, dtype=float)

    if coordinates.shape != (len(shares), 2) or not np.isfinite(coordinates).all():
        raise ValueError("Centroids must be finite x/y coordinates in population-share order")

    if not np.isfinite(distance_power) or distance_power <= 0:
        raise ValueError("Distance power must be positive and finite")

    centered_shares = _center_varying_shares(shares)

    if len(np.unique(coordinates, axis=0)) != len(coordinates):
        raise UndefinedMetricError(UndefinedMetricReason.COINCIDENT_CENTROIDS)

    numerator = 0.0
    node_count = len(shares)
    rows_per_batch = max(1, 1_000_000 // node_count)

    # ponytail: exact pairwise distances take O(n²) time; approximation requires a method decision.
    for start in range(0, node_count, rows_per_batch):
        stop = min(start + rows_per_batch, node_count)
        distances = cdist(coordinates[start:stop], coordinates)
        distances[np.arange(stop - start), np.arange(start, stop)] = np.inf

        if np.any(distances == 0):
            raise UndefinedMetricError(UndefinedMetricReason.COINCIDENT_CENTROIDS)

        # Row scaling cancels during normalization and avoids overflowing inverse powers.
        weights = (distances.min(axis=1, keepdims=True) / distances) ** distance_power
        weighted_shares = (weights @ centered_shares) / weights.sum(axis=1)
        numerator += centered_shares[start:stop] @ weighted_shares

    return float(numerator / (centered_shares @ centered_shares))


def _check_shares(population_shares: np.ndarray) -> np.ndarray:
    """Return finite one-dimensional shares in [0, 1], or raise ValueError for malformed input."""
    shares = np.asarray(population_shares, dtype=float)

    if shares.ndim != 1 or shares.size == 0 or not np.isfinite(shares).all():
        raise ValueError("Population shares must be a nonempty finite vector")

    if np.any((shares < 0) | (shares > 1)):
        raise ValueError("Population shares must lie between zero and one")

    return shares


def _center_varying_shares(shares: np.ndarray) -> np.ndarray:
    """Center validated shares, raising UndefinedMetricError when their variance is zero."""
    if np.ptp(shares) == 0:
        raise UndefinedMetricError(UndefinedMetricReason.ZERO_SHARE_VARIANCE)

    return shares - shares.mean()
