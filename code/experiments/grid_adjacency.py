"""Rook adjacency shared by square-grid experiments."""

import networkx as nx
from scipy import sparse


def build_grid_adjacency(side_length: int) -> sparse.csr_array:
    """Return open-boundary rook adjacency in row-major order for a square grid."""
    if side_length < 2:
        raise ValueError("Grid side length must be at least two")

    return nx.to_scipy_sparse_array(nx.grid_2d_graph(side_length, side_length), format="csr")
