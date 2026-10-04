"""Construct and score spatial arrangements of fixed grid population distributions."""

from enum import StrEnum
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.experiment_scores import calculate_experiment_scores
from experiments.grid_adjacency import build_grid_adjacency


class Arrangement(StrEnum):
    """Spatial arrangements of a fixed collection of cell populations."""

    CLUSTERED = "clustered"
    RANDOM = "random"
    ALTERNATING = "alternating"


def arrange_shares(
    shares: np.ndarray,
    arrangement: Arrangement,
    generator: np.random.Generator,
) -> np.ndarray:
    """Arrange a square, even-sized multiset without changing its population distribution.

    Args:
        shares (np.ndarray): One-dimensional group shares for an even square number of cells.
        arrangement (Arrangement): Clustered columns, random permutation, or alternating halves.
        generator (np.random.Generator): Advanced only for a random arrangement.

    Returns:
        np.ndarray: New square grid. Alternating pure cells are spread across their respective
            checkerboard halves rather than collected at one end.

    Raises:
        ValueError: The cell count is unsuitable or too many shares lie on one side of 0.5 for the
            alternating arrangement.
    """
    side = int(np.sqrt(len(shares)))

    if side * side != len(shares) or side % 2:
        raise ValueError("Share examples require an even square number of cells")

    sorted_shares = np.sort(shares)

    if arrangement == Arrangement.CLUSTERED:
        return sorted_shares.reshape(side, side, order="F")
    if arrangement == Arrangement.RANDOM:
        return generator.permutation(shares).reshape(side, side)

    checkerboard = (np.indices((side, side)).sum(axis=0) % 2 == 0).ravel()
    even_positions = np.flatnonzero(checkerboard)
    odd_positions = np.flatnonzero(~checkerboard)
    low_shares = sorted_shares[sorted_shares < 0.5]
    high_shares = sorted_shares[sorted_shares > 0.5]

    if max(len(low_shares), len(high_shares)) > len(shares) // 2:
        raise ValueError("Alternating arrangements need at most half the cells on each side of 0.5")

    arranged = np.full(len(shares), 0.5)
    arranged[odd_positions[np.linspace(0, len(odd_positions) - 1, len(low_shares), dtype=int)]] = (
        low_shares
    )
    arranged[
        even_positions[np.linspace(0, len(even_positions) - 1, len(high_shares), dtype=int)]
    ] = high_shares[::-1]

    return arranged.reshape(side, side)


def build_population_share_distributions() -> dict[str, np.ndarray]:
    """Return the three balanced 144-cell share distributions used by grid arrangements."""
    return {
        "moderate": np.repeat([0.25, 0.75], [72, 72]),
        "many_mixed": np.repeat([0.0, 0.5, 1.0], [36, 72, 36]),
        "mostly_mixed": np.repeat([0.0, 0.5, 1.0], [18, 108, 18]),
    }


def run_grid_pop_share_arrangements(data_directory: Path, seed: int = 20260918) -> None:
    """Save the nine arranged share grids and their metric scores.

    Args:
        data_directory (Path): Destination for named grid arrays and Parquet scores.
        seed (int): Seed for random share arrangements, default 20260918.

    Raises:
        OSError: An experiment output cannot be written.
    """
    generator = np.random.default_rng(seed)
    share_distributions = build_population_share_distributions()
    grids = {}
    score_rows = []
    adjacency = build_grid_adjacency(12)

    for distribution_name, shares in share_distributions.items():
        for arrangement in Arrangement:
            name = f"{distribution_name}_{arrangement}"
            grid = arrange_shares(shares, arrangement, generator)
            grids[name] = grid
            score_rows.append(
                {
                    "example": name,
                    "seed": seed,
                    **calculate_experiment_scores(
                        adjacency, grid.ravel(), 1 - grid.ravel()
                    ).to_record(),
                }
            )

    data_directory.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(data_directory / "share_grids.npz", **grids)
    pd.DataFrame(score_rows).to_parquet(data_directory / "share_scores.parquet", index=False)
