"""Sample binary grids and save their Capy and Moran score distributions."""

from pathlib import Path

import numpy as np
import pandas as pd
from capy_metrics import MoranWeightType, build_moran_weights, capy, morans_I
from scipy.ndimage import gaussian_filter
from tqdm import trange

from experiments.grid_adjacency import build_grid_adjacency


def build_binary_grid(clustering: str, seed: int, swap_steps: int = 20000) -> np.ndarray:
    """Build a balanced 100-cell arrangement using swaps, permutation, or smoothed noise.

    Low clustering accepts swaps increasing edges between different groups, and accepts other
    swaps with probability 0.01. Medium clustering is a uniform permutation. High clustering thresholds
    Gaussian-smoothed noise (sigma 1.6) by rank to retain exactly 50 first-group cells.

    Args:
        clustering (str): low, medium, or high.
        seed (int): Independent generator seed for this sample.
        swap_steps (int): Number of low-clustering swap proposals, default 20,000.

    Returns:
        np.ndarray: Binary 10×10 grid, with exactly half its cells equal to one.

    Raises:
        ValueError: The clustering class is unsupported or the iteration count is negative.
    """
    if clustering not in ("low", "medium", "high") or swap_steps < 0:
        raise ValueError("Use low, medium, or high clustering and nonnegative swap steps")

    rng = np.random.default_rng(seed)
    assignment = np.repeat([1, 0], 50).astype(np.int8)

    if clustering == "high":
        smoothed_noise = gaussian_filter(rng.random((10, 10)), sigma=1.6)
        assignment[:] = 0
        assignment[np.argsort(smoothed_noise.ravel(), kind="stable")[-50:]] = 1

        return assignment.reshape(10, 10)

    rng.shuffle(assignment)

    if clustering == "medium":
        return assignment.reshape(10, 10)

    adjacency = build_grid_adjacency(10)
    neighbors_by_node = [
        adjacency.indices[adjacency.indptr[node] : adjacency.indptr[node + 1]]
        for node in range(100)
    ]
    first_group_nodes = np.flatnonzero(assignment)
    second_group_nodes = np.flatnonzero(1 - assignment)

    for _ in range(swap_steps):
        first_position, second_position = rng.integers(50, size=2)
        first_node, second_node = (
            first_group_nodes[first_position],
            second_group_nodes[second_position],
        )
        unlike_edge_change = 0

        for node, other_swapped_node in ((first_node, second_node), (second_node, first_node)):
            neighbor_nodes = neighbors_by_node[node]
            # The edge between the swapped nodes remains between different groups.
            neighbor_nodes = neighbor_nodes[neighbor_nodes != other_swapped_node]
            unlike_edge_change += int(
                np.sum(2 * (assignment[node] == assignment[neighbor_nodes]) - 1)
            )

        if unlike_edge_change > 0 or rng.random() < 0.01:
            assignment[first_node], assignment[second_node] = 0, 1
            first_group_nodes[first_position], second_group_nodes[second_position] = (
                second_node,
                first_node,
            )

    return assignment.reshape(10, 10)


def run_grid_distributions(data_directory: Path, samples: int = 10000, seed: int = 1000) -> None:
    """Save independent seeded samples and their regular Capy and row-standardized Moran scores.

    Each cell contains 100 people of a single group. Defaults produce 10,000 samples per class.

    Args:
        data_directory (Path): Destination for score rows and the first grid of each class.
        samples (int): Independent samples per class, default 10,000.
        seed (int): First sample seed, reused across classes and incremented per sample; default 1000.

    Raises:
        ValueError: The sample count is not positive.
        OSError: An output cannot be written.
    """
    if samples < 1:
        raise ValueError("Samples must be positive")

    adjacency = build_grid_adjacency(10)
    moran_weights = build_moran_weights(adjacency, MoranWeightType.ROW_STANDARDIZED)
    score_rows = []
    example_grids = {}

    for clustering in ("low", "medium", "high"):
        for sample in trange(samples, desc=f"{clustering} clustering", disable=None):
            grid = build_binary_grid(clustering, seed + sample)
            first_population = 100 * grid.ravel().astype(float)

            score_rows.append(
                {
                    "kind": clustering,
                    "seed": seed + sample,
                    "capy": capy(adjacency, first_population, 100 - first_population),
                    "moran_row_standardized": morans_I(moran_weights, grid.ravel()),
                }
            )

            if sample == 0:
                example_grids[clustering] = grid

    data_directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(score_rows).to_parquet(data_directory / "distribution_scores.parquet", index=False)
    np.savez_compressed(data_directory / "distribution_examples.npz", **example_grids)
