"""Finite and periodic triangular-lattice populations and their score calculations."""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse

from experiments.experiment_scores import calculate_example_scores

# Binary transcription of the lattice patterns in Reardon and O'Sullivan (2004), p. 126. Rows run
# top to bottom; odd rows shift left by half a lattice spacing.
PRINTED_PATTERNS = {
    "upper_left": (
        "0001000000",
        "0100000010",
        "0000010000",
        "0001000000",
        "1000000100",
        "0000010000",
        "0010000001",
        "1000000100",
        "0000100000",
        "0010000001",
        "0000100000",
        "0010000001",
    ),
    "upper_right": (
        "1001001001",
        "0010010010",
        "1001001001",
        "0010010010",
        "1001001001",
        "0010010010",
        "1001001001",
        "0010010010",
        "1001001000",
        "0010010010",
        "1001001000",
        "0010010010",
    ),
    "lower_left": (
        "0000000000",
        "1111001111",
        "1110001110",
        "0110000110",
        "0100000100",
        "0000000000",
        "0000000000",
        "1001111001",
        "0001110001",
        "0000110000",
        "0000100000",
        "0000000000",
    ),
    "lower_right": (
        "1011011011",
        "1001001001",
        "0000000000",
        "0110110110",
        "0100100100",
        "0000000000",
        "1011011011",
        "1001001001",
        "0000000000",
        "0110110110",
        "0100100100",
        "0000000000",
    ),
}


def build_triangular_adjacency(rows: int, columns: int, *, periodic: bool) -> sparse.csr_array:
    """Build six-neighbor adjacency on left-staggered rows, optionally wrapping a period cell.

    Periodic rows must be even to preserve the stagger at the seam. Multiple translated neighbors
    landing in the same period-cell position contribute multiplicity, not one edge. This matters
    for the two-row idealized independent-set pattern.

    Args:
        rows (int): Number of staggered rows, at least two.
        columns (int): Number of columns, at least three.
        periodic (bool): Wrap neighboring positions around the rectangle when True.

    Returns:
        sparse.csr_array: Symmetric adjacency in flattened row-major order.

    Raises:
        ValueError: Dimensions are too small or periodic rows are odd.
    """
    if rows < 2 or columns < 3 or (periodic and rows % 2):
        raise ValueError("Use at least 2 rows, 3 columns, and even periodic row count")

    adjacency = np.zeros((rows * columns, rows * columns))

    for row in range(rows):
        offset = 1 if row % 2 == 0 else -1

        for column in range(columns):
            neighbors = [
                (row, column - 1),
                (row, column + 1),
                (row - 1, column),
                (row - 1, column + offset),
                (row + 1, column),
                (row + 1, column + offset),
            ]

            for neighbor_row, neighbor_column in neighbors:
                if periodic:
                    neighbor_row %= rows
                    neighbor_column %= columns
                if 0 <= neighbor_row < rows and 0 <= neighbor_column < columns:
                    adjacency[row * columns + column, neighbor_row * columns + neighbor_column] += 1

    return sparse.csr_array(adjacency)


def build_triangular_lattice_results() -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """Calculate finite and periodic scores and build the eight corresponding lattice windows.

    Each dot represents one person: 1 denotes Black and 0 denotes White. Finite calculations use
    the four 12×10 arrays in PRINTED_PATTERNS without connecting opposite edges. Periodic
    calculations repeat a tile, connecting neighboring dots across its opposite edges.

    The densely dispersed arrangement (upper_right) repeats a 2-row, 3-column tile of isolated
    Black dots. The small-cluster arrangement (lower_right) repeats a 6-row, 3-column tile.
    The sparsely dispersed (upper_left) and large-cluster (lower_left) arrangements repeat their
    full 12×10 arrays. Repeating the sparse arrangement creates one adjacent Black pair across
    the tile boundary, so its Black dots no longer form an independent set.

    All returned display windows contain 12×10 dots, regardless of the repeating tile's size.
    Exact Capy excludes pairing a person with themself. Local-environment scores include each
    dot and its neighbors through I+A, where I is the identity and A is the adjacency matrix.

    Returns:
        tuple[pd.DataFrame, dict[str, np.ndarray]]: Score rows for each arrangement under finite
            (printed) and periodic interpretations, plus binary 12×10 display arrays keyed by
            interpretation and arrangement, such as printed_upper_left.
    """
    records = []
    windows = {}

    for name, binary_rows in PRINTED_PATTERNS.items():
        printed = np.array([[int(value) for value in row] for row in binary_rows])
        period = printed

        if name == "upper_right":
            period = np.array([[1, 0, 0], [0, 0, 1]])
        elif name == "lower_right":
            period = printed[:6, :3]

        for interpretation, pattern in (("printed", printed), ("periodic", period)):
            # Two row periods keep all six neighbors distinct in the binary adjacency matrix.
            scoring_pattern = np.tile(pattern, (2, 1)) if pattern.shape[0] == 2 else pattern
            adjacency = build_triangular_adjacency(
                *scoring_pattern.shape, periodic=interpretation == "periodic"
            )
            black_population = scoring_pattern.ravel()

            closed_adj_nbhd = adjacency + sparse.eye_array(len(black_population))

            local_black_share = (
                closed_adj_nbhd
                @ black_population
                / (closed_adj_nbhd @ np.ones(len(black_population)))
            )
            exposure = float(
                (1 - black_population) @ local_black_share / (1 - black_population).sum()
            )
            records.append(
                {
                    "panel": name,
                    "interpretation": interpretation,
                    "period_rows": pattern.shape[0],
                    "period_columns": pattern.shape[1],
                    "white_exposure_to_black": exposure,
                    # NOTE: Distict people is True will call capy_exact
                    **calculate_example_scores(
                        adjacency, black_population, 1 - black_population, distinct_people=True
                    ),
                }
            )
            window = np.tile(pattern, (12 // pattern.shape[0] + 1, 10 // pattern.shape[1] + 1))[
                :12, :10
            ]
            windows[f"{interpretation}_{name}"] = window

    return pd.DataFrame(records), windows


def run_triangular_lattices(data_directory: Path) -> None:
    """Save finite and periodic score rows and the corresponding lattice windows for rendering.

    Args:
        data_directory (Path): Destination for triangular_scores.parquet and
            triangular_windows.npz.

    Raises:
        OSError: The destination cannot be created or either output cannot be written.
    """
    scores_df, windows = build_triangular_lattice_results()
    data_directory.mkdir(parents=True, exist_ok=True)
    scores_df.to_parquet(data_directory / "triangular_scores.parquet", index=False)
    np.savez_compressed(data_directory / "triangular_windows.npz", allow_pickle=False, **windows)
