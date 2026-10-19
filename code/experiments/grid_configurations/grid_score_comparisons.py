"""Compute and save scores for generated grid configurations."""

from pathlib import Path

import numpy as np
import pandas as pd
from itertools import product

from experiments.experiment_scores import calculate_experiment_scores
from experiments.grid_adjacency import build_grid_adjacency
from experiments.grid_configurations.grid_pop_share_arrangements import (
    Arrangement,
    arrange_shares,
    build_population_share_distributions,
)
from experiments.grid_configurations.grid_reference_scores import build_grid_reference_scores


def tune_binary_grid(kind: str, generator: np.random.Generator) -> np.ndarray:
    """Tune a balanced 12×12 grid to a target number of edges between different groups.

    Target ranges are 30–50 edges (few), 120–145 (intermediate), and 210–235 (many).
    Swaps preserve the 72/72 cell counts. An annealed distance-to-target acceptance rule stops
    after reaching within one edge of the sampled target, following at least 251 proposals.

    Args:
        kind (str): few_unlike, intermediate, or many_unlike edge-count class.
        generator (np.random.Generator): Experiment-owned random stream, advanced in place.

    Returns:
        np.ndarray: Balanced 12×12 binary grid satisfying the selected edge-count range.

    Raises:
        KeyError: The edge-count class is unsupported.
        RuntimeError: No suitable arrangement is found within 60,000 proposals.
    """
    lower, upper = {"few_unlike": (30, 50), "intermediate": (120, 145), "many_unlike": (210, 235)}[
        kind
    ]
    target = int(generator.integers(lower, upper + 1))
    grid = np.zeros((12, 12), dtype=np.int8)

    if kind == "few_unlike":
        grid[:6] = 1
        grid = np.rot90(grid, int(generator.integers(4))).copy()
    elif kind == "many_unlike":
        grid = (np.indices((12, 12)).sum(axis=0) % 2).astype(np.int8)
    else:
        grid = generator.permutation(np.repeat([0, 1], 72)).reshape(12, 12)

    def count_unlike_edges() -> int:
        return int(np.sum(grid[:, 1:] != grid[:, :-1]) + np.sum(grid[1:] != grid[:-1]))

    edge_count = count_unlike_edges()

    for step in range(60000):
        if lower <= edge_count <= upper and abs(edge_count - target) <= 1 and step > 250:
            return grid

        first = np.argwhere(grid == 1)[generator.integers(72)]
        second = np.argwhere(grid == 0)[generator.integers(72)]
        grid[tuple(first)], grid[tuple(second)] = 0, 1

        proposed_count = count_unlike_edges()

        # NOTE: Metropolis-style acceptance rule
        improvement = abs(edge_count - target) - abs(proposed_count - target)
        temperature = max(0.06, 2.5 * (1 - step / 60000))

        if improvement >= 0 or generator.random() < np.exp(improvement / temperature):
            edge_count = proposed_count
        else:
            grid[tuple(first)], grid[tuple(second)] = 1, 0

    raise RuntimeError(f"Could not construct a {kind} binary grid")


def build_perturbed_share_grids(seed: int) -> tuple[dict[str, np.ndarray], pd.DataFrame]:
    """Build perturbed share grids with distribution, arrangement, and sample identities.

    Args:
        seed (int): Seed for the locally owned random generator.

    Returns:
        tuple[dict[str, np.ndarray], pd.DataFrame]: Named arrays and one identity row per grid.
            Six examples cover each combination of three distributions and three arrangements.
    """
    generator = np.random.default_rng(seed)
    share_distributions = build_population_share_distributions()
    grids = {}
    identities = []

    for (distribution_name, shares), arrangement, sample in product(
        share_distributions.items(), Arrangement, range(6)
    ):
        grid = arrange_shares(shares, arrangement, generator)

        if arrangement != Arrangement.RANDOM:
            grid = np.rot90(grid, int(generator.integers(4)))

            if generator.random() < 0.5:
                grid = np.fliplr(grid)

            grid = grid.copy().ravel()

            for _ in range(2 * sample):
                first, second = generator.choice(len(grid), size=2, replace=False)

                while grid[first] == grid[second]:
                    first, second = generator.choice(len(grid), size=2, replace=False)
                grid[first], grid[second] = grid[second], grid[first]

        name = f"{distribution_name}_{arrangement}_{sample + 1:02d}"
        grids[name] = grid.reshape(12, 12)
        identities.append(
            {
                "example": name,
                "family": "shares",
                "category": distribution_name,
                "arrangement": arrangement,
                "sample": sample + 1,
            }
        )

    return grids, pd.DataFrame(identities)


def run_grid_score_comparisons(data_directory: Path, seed: int = 20260918) -> None:
    """Save 60 binary-person grids and 54 continuous-share grids with their scores.

    Binary grids represent one person per cell and therefore use exact spatial Capy. Share grids
    represent continuous mass and use quadratic Capy.

    Args:
        data_directory (Path): Destination for the grid arrays and score table; created if absent.
        seed (int): Reproducible generator seed, default 20260918.

    Raises:
        RuntimeError: A binary grid cannot be tuned within its proposal limit.
        OSError: An output cannot be written.
    """
    generator = np.random.default_rng(seed)
    grids, identities_df = build_perturbed_share_grids(seed)
    identities = identities_df.to_dict("records")
    rows = []
    adjacency = build_grid_adjacency(12)
    seen_grids = set()

    for kind in ("few_unlike", "intermediate", "many_unlike"):
        sample = 0

        while sample < 20:
            grid = tune_binary_grid(kind, generator)

            if grid.tobytes() in seen_grids:
                continue

            seen_grids.add(grid.tobytes())
            sample += 1
            name = f"binary_{kind}_{sample:02d}"
            grids[name] = grid
            identities.append(
                {
                    "example": name,
                    "family": "binary",
                    "category": kind,
                    "arrangement": None,
                    "sample": sample,
                }
            )

    for identity in identities:
        grid = grids[identity["example"]]
        rows.append(
            {
                **identity,
                "seed": seed,
                **calculate_experiment_scores(
                    adjacency,
                    grid.ravel(),
                    1 - grid.ravel(),
                    distinct_people=identity["family"] == "binary",
                ).to_record(),
            }
        )

    references_df = build_grid_reference_scores()
    data_directory.mkdir(parents=True, exist_ok=True)

    np.savez_compressed(data_directory / "grid_arrays.npz", allow_pickle=False, **grids)
    pd.DataFrame(rows).to_parquet(data_directory / "grid_scores.parquet", index=False)

    references_df.to_parquet(data_directory / "reference_scores.parquet", index=False)
