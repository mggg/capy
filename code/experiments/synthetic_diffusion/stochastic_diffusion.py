"""Reuse long-run replicate scores and simulate consistently calibrated early snapshots."""

from pathlib import Path

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

SNAPSHOT_STEPS = (0, 25, 100, 250, 500, 800)
DEMOGRAPHIC_HORIZON = 4000
DEMOGRAPHIES = ("constant", "growth", "decline")
SOURCE_METRICS = {
    "Dissimilarity": "dissimilarity",
    "Theil H": "entropy_index",
    "Capy C": "capy",
    "Moran I (I+A)": "moran_with_self",
    "Moran I (P)": "moran_row_standardized",
}


def move_population(
    population_counts: np.ndarray,
    neighbor_indices_by_node: list[np.ndarray],
    rng: np.random.Generator,
    move_probability: float = 0.2,
) -> np.ndarray:
    """Move each person independently to a uniform neighbor, conserving integer population.

    Args:
        population_counts (np.ndarray): Nonnegative integer counts in node order.
        neighbor_indices_by_node (list[np.ndarray]): Neighbor indices for every node;
            no node may be isolated.
        rng (np.random.Generator): Owned by the simulation; its random state advances.
        move_probability (float): Probability of moving per step, default 0.2.

    Returns:
        np.ndarray: New population counts.
    """
    updated_population = np.zeros_like(population_counts)

    for node_index, neighbor_indices in enumerate(neighbor_indices_by_node):
        if population_counts[node_index] == 0:
            continue

        destination_probabilities = [
            1 - move_probability,
            *([move_probability / len(neighbor_indices)] * len(neighbor_indices)),
        ]
        destination_counts = rng.multinomial(
            int(population_counts[node_index]), destination_probabilities
        )
        updated_population[node_index] += destination_counts[0]
        updated_population[neighbor_indices] += destination_counts[1:]

    return updated_population


def read_cached_stochastic_scores(source_directory: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the supplied 4,000-step replicate runs, retaining their first 800 steps.

    Args:
        source_directory (Path): Source root containing scripts/synthetic/
            stochastic_data and both stochastic_diffusion_*abc_long_scores.csv files.

    Returns:
        tuple[pd.DataFrame, pd.DataFrame]: Complete early replicate scores and source coverage
            accounting. Partial early histories are excluded as whole replicates and recorded.

    Raises:
        OSError: A source CSV cannot be read.
        ValueError: Replicate identities repeat, expected variants are missing, or scores are invalid.
    """
    replicate_score_tables = []
    replicate_coverage_tables = []

    for source_experiment_number, movement_rule in ((2, "one_sided"), (3, "two_sided")):
        source_path = (
            source_directory
            / "scripts/synthetic/stochastic_data"
            / (f"stochastic_diffusion_{source_experiment_number}abc_long_scores.csv")
        )
        source_scores_df = pd.read_csv(source_path)
        demography_by_source_variant = {
            f"{source_experiment_number}{variant_letter}": demography
            for variant_letter, demography in zip("ABC", DEMOGRAPHIES, strict=True)
        }

        if (
            set(source_scores_df.variant) != set(demography_by_source_variant)
            or source_scores_df.step.max() != DEMOGRAPHIC_HORIZON
        ):
            raise ValueError(f"Expected three 4,000-step demographic variants: {source_path}")

        if source_scores_df.duplicated(["variant", "replicate", "step"]).any():
            raise ValueError(f"Repeated stochastic replicate observations: {source_path}")

        early_scores_df = source_scores_df.loc[source_scores_df.step.between(0, 800)].copy()

        if not np.isfinite(early_scores_df[list(SOURCE_METRICS)].to_numpy()).all():
            raise ValueError(f"Nonfinite early stochastic scores: {source_path}")

        replicate_step_counts_df = early_scores_df.groupby(["variant", "replicate"]).step.agg(
            ["min", "max", "count"]
        )
        replicate_step_counts_df["included"] = (
            replicate_step_counts_df["min"].eq(0)
            & replicate_step_counts_df["max"].eq(800)
            & replicate_step_counts_df["count"].eq(801)
        )
        replicate_coverage_df = replicate_step_counts_df.reset_index().rename(
            columns={"min": "first_step", "max": "last_step", "count": "observation_count"}
        )
        replicate_coverage_df["movement"] = movement_rule
        replicate_coverage_df["demography"] = replicate_coverage_df.variant.map(
            demography_by_source_variant
        )
        replicate_coverage_tables.append(replicate_coverage_df.drop(columns="variant"))
        early_scores_df = early_scores_df.merge(
            replicate_coverage_df.loc[replicate_coverage_df.included, ["variant", "replicate"]],
            on=["variant", "replicate"],
            validate="many_to_one",
        )

        if set(early_scores_df.variant) != set(demography_by_source_variant):
            raise ValueError(
                f"No complete early replicates for a demographic variant: {source_path}"
            )

        early_scores_df = early_scores_df.rename(columns=SOURCE_METRICS)
        early_scores_df["demography"] = early_scores_df.variant.map(demography_by_source_variant)
        early_scores_df["movement"] = movement_rule
        early_scores_df["demographic_horizon"] = DEMOGRAPHIC_HORIZON
        replicate_score_tables.append(early_scores_df.drop(columns="variant"))

    return pd.concat(replicate_score_tables, ignore_index=True), pd.concat(
        replicate_coverage_tables, ignore_index=True
    )


def simulate_early_snapshots(move_both_groups: bool, demography: str, seed: int) -> np.ndarray:
    """Return six integer snapshots using 4,000-step demographic rates through step 800.

    Args:
        move_both_groups (bool): Move both populations when True, only the first when False.
        demography (str): constant, growth, or decline of the first population.
        seed (int): Seed for the example trajectory, independent of the cached replicate traces.

    Returns:
        np.ndarray: Counts ordered (snapshot, group, row, column). Each initial cell has 1,000
            people. Movement probability is 0.2; births/deaths follow movement. Neighbor order is
            down/up/right/left so the seeded stream agrees with the source simulation.

    Raises:
        ValueError: The demographic variant is unsupported.
    """
    if demography not in DEMOGRAPHIES:
        raise ValueError(f"Unsupported demography: {demography}")

    rng = np.random.default_rng(seed)
    first_group_population = np.zeros((20, 20), dtype=np.int64)
    first_group_population[5:15, 5:15] = 1000
    first_group_population = first_group_population.ravel()
    second_group_population = 1000 - first_group_population

    neighbor_indices_by_node = []

    for node_index in range(400):
        row, column = divmod(node_index, 20)
        neighbor_positions = (
            (row + 1, column),
            (row - 1, column),
            (row, column + 1),
            (row, column - 1),
        )
        neighbor_indices = [
            neighbor_row * 20 + neighbor_column
            for neighbor_row, neighbor_column in neighbor_positions
            if 0 <= neighbor_row < 20 and 0 <= neighbor_column < 20
        ]
        neighbor_indices_by_node.append(np.array(neighbor_indices))

    population_snapshots = []

    for step in range(801):
        if step in SNAPSHOT_STEPS:
            population_snapshots.append(
                np.stack([first_group_population, second_group_population]).reshape(2, 20, 20)
            )

        if step == 800:
            break

        first_group_population = move_population(
            first_group_population, neighbor_indices_by_node, rng
        )

        if move_both_groups:
            second_group_population = move_population(
                second_group_population, neighbor_indices_by_node, rng
            )

        if demography == "growth":
            first_group_population += rng.binomial(
                first_group_population, 2 ** (1 / DEMOGRAPHIC_HORIZON) - 1
            )
        elif demography == "decline":
            first_group_population = rng.binomial(
                first_group_population, (1 / 3) ** (1 / DEMOGRAPHIC_HORIZON)
            )

    return np.array(population_snapshots)


def run_stochastic_diffusion(data_directory: Path, source_directory: Path) -> None:
    """Save cached early replicate scores and regenerate independent, consistently calibrated grids.

    Args:
        data_directory (Path): Result root. The one_sided and two_sided subfolders each receive
            replicate scores, trace quantiles, coverage, and snapshots with step coordinates.
        source_directory (Path): Root containing scripts/synthetic/stochastic_data.

    Raises:
        OSError: An input cannot be read or an output cannot be written.
        ValueError: Cached observations are malformed or a variant has no complete early histories.
    """
    replicate_scores_df, replicate_coverage_df = read_cached_stochastic_scores(source_directory)

    for movement_rule in tqdm(
        ("one_sided", "two_sided"), desc="Stochastic snapshots", unit="family"
    ):
        movement_scores_df = replicate_scores_df.loc[replicate_scores_df.movement.eq(movement_rule)]
        movement_coverage_df = replicate_coverage_df.loc[
            replicate_coverage_df.movement.eq(movement_rule)
        ]
        trace_summary_df = (
            movement_scores_df.groupby(["movement", "demography", "step"])[
                list(SOURCE_METRICS.values())
            ]
            .quantile(np.array([0.1, 0.5, 0.9]))
            .rename_axis(index=["movement", "demography", "step", "quantile"])
            .reset_index()
        )
        snapshot_arrays = {"snapshot_steps": np.array(SNAPSHOT_STEPS)}

        for seed_offset, demography in enumerate(DEMOGRAPHIES):
            snapshot_arrays[f"{movement_rule}_{demography}"] = simulate_early_snapshots(
                movement_rule == "two_sided", demography, 20260918 + seed_offset
            )

        movement_directory = data_directory / movement_rule
        movement_directory.mkdir(parents=True, exist_ok=True)
        movement_scores_df.to_parquet(movement_directory / "stochastic_scores.parquet", index=False)
        trace_summary_df.to_parquet(
            movement_directory / "stochastic_trace_summary.parquet", index=False
        )
        movement_coverage_df.to_parquet(
            movement_directory / "source_replicate_coverage.parquet", index=False
        )
        np.savez_compressed(
            movement_directory / "stochastic_states.npz", allow_pickle=False, **snapshot_arrays
        )
