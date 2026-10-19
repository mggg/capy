"""Generate, measure, and save population grids for Capy's intensity–layout comparison."""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import sparse
from tqdm import tqdm

from experiments.experiment_scores import ExperimentScores, calculate_experiment_scores
from experiments.grid_adjacency import build_grid_adjacency
from experiments.grid_configurations.factorization_layout import (
    GRID_NODE_COUNT,
    GRID_SIDE_LENGTH,
    swap_toward_target_layout,
)


class ShareFamily(StrEnum):
    """Supported distributions of unit population shares, in seeded draw order."""

    BETA = "beta"
    SHRUNK_BINARY = "shrunk_binary"
    UNIFORM_BAND = "uniform_band"


class FactorQuadrant(StrEnum):
    """Intensity/layout regions used to select and color example grids."""

    WEAK_CLUSTERED = "weak_clustered"
    STRONG_CLUSTERED = "strong_clustered"
    WEAK_DISPERSED = "weak_dispersed"
    STRONG_DISPERSED = "strong_dispersed"


QUADRANT_CENTERS = {
    FactorQuadrant.WEAK_CLUSTERED: (0.25, 0.6),
    FactorQuadrant.STRONG_CLUSTERED: (0.75, 0.6),
    FactorQuadrant.WEAK_DISPERSED: (0.25, -0.2),
    FactorQuadrant.STRONG_DISPERSED: (0.75, -0.2),
}
EXAMPLE_SHARE_TARGETS = (0.45, 0.33, 0.21, 0.09)


@dataclass(frozen=True)
class FactorizationScores:
    """Endpoint-weighted factors and the comparison metrics measured on one grid.

    endpoint_share uses masses t_i(Wt)_i. intensity is their normalized share variance;
    layout is normalized pair covariance. Comparison metrics use their own population/weight
    conventions and retain undefined reasons through ExperimentScores.
    """

    endpoint_share: float
    intensity: float
    layout: float
    comparison_scores: ExperimentScores

    def to_record(self) -> dict[str, float | str | None]:
        """Flatten factors and metrics, preserving the saved table's reason-column convention."""
        return {
            "endpoint_share": self.endpoint_share,
            "intensity": self.intensity,
            "layout": self.layout,
            "endpoint_share_undefined_reason": None,
            "intensity_undefined_reason": None,
            "layout_undefined_reason": None,
            **self.comparison_scores.to_record(),
        }


@dataclass(frozen=True)
class FactorizationSample:
    """One accepted target, its realized grid, and scores computed on that grid.

    Arrays use row-major node order. Targets describe sampling choices, not constraints satisfied
    exactly by the realized endpoint-weighted intensity or population share.
    """

    seed: int
    share_family: ShareFamily
    target_group_share: float
    target_intensity: float
    target_layout: float
    shares: np.ndarray
    total_population: np.ndarray
    scores: FactorizationScores

    def to_record(self) -> dict[str, float | str | None]:
        """Flatten the target metadata and scores; grid arrays are saved separately."""
        return {
            "seed": self.seed,
            "share_family": self.share_family,
            "target_group_share": self.target_group_share,
            "target_intensity": self.target_intensity,
            "target_layout": self.target_layout,
            **self.scores.to_record(),
        }


@dataclass(frozen=True)
class SelectedExample:
    """One grid's rank within a quadrant and population-share target.

    Rank one identifies the grid illustration; ranks one through ten enter score panels.
    The same seed can serve more than one target.
    """

    quadrant: FactorQuadrant
    target_group_share: float
    rank: int
    seed: int


def run_capy_factorization(output_directory: Path, targets: int = 7000) -> None:
    """Generate seeds 0 through targets-1 on two workers and save scores and all accepted grids.

    Args:
        output_directory (Path): Destination for factorization_scores.parquet, grids.npz,
            selected_examples.parquet, and run_summary.parquet. Existing matching outputs are
            replaced after computation and example selection.
        targets (int): Positive number of attempted targets, default 7,000.

    Raises:
        ValueError: No targets were requested, no grids were accepted, or an example share band
            has no candidates. Existing files are preserved in these cases.
        OSError: Results cannot be written. Writes are sequential; rerun after interruption.
    """
    if targets <= 0:
        raise ValueError("Request a positive number of factorization targets")

    with ProcessPoolExecutor(max_workers=2) as pool:
        samples = [
            sample
            for sample in tqdm(
                pool.map(generate_factorization_sample, range(targets), chunksize=50),
                total=targets,
                desc="Capy factorization targets",
            )
            if sample is not None
        ]

    if not samples:
        raise ValueError("No factorization targets produced accepted grids")

    scores_df = pd.DataFrame([sample.to_record() for sample in samples])
    examples = select_factorization_examples(scores_df)
    examples_df = pd.DataFrame([asdict(example) for example in examples])

    output_directory.mkdir(parents=True, exist_ok=True)
    scores_df.to_parquet(output_directory / "factorization_scores.parquet", index=False)
    np.savez_compressed(
        output_directory / "grids.npz",
        seed=np.array([sample.seed for sample in samples]),
        shares=np.stack(
            [sample.shares.reshape(GRID_SIDE_LENGTH, GRID_SIDE_LENGTH) for sample in samples]
        ),
        total_population=np.stack(
            [
                sample.total_population.reshape(GRID_SIDE_LENGTH, GRID_SIDE_LENGTH)
                for sample in samples
            ]
        ),
        allow_pickle=False,
    )
    pd.DataFrame(
        [{"attempted": targets, "accepted": len(samples), "rejected": targets - len(samples)}]
    ).to_parquet(output_directory / "run_summary.parquet", index=False)
    examples_df.to_parquet(output_directory / "selected_examples.parquet", index=False)


def generate_factorization_sample(seed: int) -> FactorizationSample | None:
    """Generate one seeded target; return None if its realized layout misses by more than 0.03.

    Population masses are lognormal with log-mean log(100), log-standard-deviation 0.6.
    Target share, intensity, and layout are uniform on [0.05,0.5], [0,1], and [-0.6,1].

    Args:
        seed (int): Nonnegative seed for population draws, targets, and swap proposals.

    Returns:
        FactorizationSample | None: Accepted grid with recomputed scores, or None when either
            the incremental or recomputed layout misses the target. Arrays belong to the sample.

    Raises:
        ValueError: The seed is invalid or the resulting grid cannot be scored.
    """
    rng = np.random.default_rng(seed)
    total_population = rng.lognormal(np.log(100), 0.6, GRID_NODE_COUNT)
    target_share = float(rng.uniform(0.05, 0.5))
    target_intensity = float(rng.uniform(0, 1))
    target_layout = float(rng.uniform(-0.6, 1.0))
    shares, family = _draw_share_multiset(rng, target_share, target_intensity)

    shares, total_population, estimated_layout = swap_toward_target_layout(
        shares, total_population, target_layout, rng
    )

    if abs(estimated_layout - target_layout) > 0.03:
        return None

    scores = calculate_factorization_scores(shares, total_population)

    if abs(scores.layout - target_layout) > 0.03:
        return None

    return FactorizationSample(
        seed=seed,
        share_family=family,
        target_group_share=target_share,
        target_intensity=target_intensity,
        target_layout=target_layout,
        shares=shares,
        total_population=total_population,
        scores=scores,
    )


def _draw_share_multiset(
    rng: np.random.Generator, target_share: float, target_intensity: float
) -> tuple[np.ndarray, ShareFamily]:
    """Draw 256 shares from a beta, shrunk-binary, or feasible uniform-band distribution.

    The supplied generator advances in place. A uniform band that cannot attain the requested
    intensity is replaced by one of the other two families. Realized moments may miss targets.

    Args:
        rng (np.random.Generator): Stream used to choose a family and draw shares.
        target_share (float): Requested mean in [0.05, 0.5].
        target_intensity (float): Requested variance divided by mean*(1-mean), in [0, 1].

    Returns:
        tuple[np.ndarray, ShareFamily]: Length-256 shares in [0, 1] and the family actually used.
    """
    families = tuple(ShareFamily)
    family = families[int(rng.integers(3))]

    if family == ShareFamily.UNIFORM_BAND and target_intensity > target_share / (
        3 * (1 - target_share)
    ):
        family = families[int(rng.integers(2))]

    if family == ShareFamily.BETA:
        concentration = max(1 / max(target_intensity, 1e-3) - 1, 1e-3)
        shares = rng.beta(
            target_share * concentration + 1e-9,
            (1 - target_share) * concentration + 1e-9,
            GRID_NODE_COUNT,
        )
    elif family == ShareFamily.SHRUNK_BINARY:
        binary = (rng.permutation(GRID_NODE_COUNT) < round(target_share * GRID_NODE_COUNT)).astype(
            float
        )
        shares = target_share + np.sqrt(target_intensity) * (binary - target_share)
    else:
        half_width = min(
            np.sqrt(3 * target_intensity * target_share * (1 - target_share)),
            target_share,
            1 - target_share,
        )
        shares = rng.uniform(target_share - half_width, target_share + half_width, GRID_NODE_COUNT)

    return np.clip(shares, 0, 1), family


def calculate_factorization_scores(
    shares: np.ndarray, total_population: np.ndarray
) -> FactorizationScores:
    """Measure standard scores, endpoint-weighted Capy factors, isolation, and exposure.

    Inputs are aligned 256-cell shares and positive population masses. With W=I+A,
    endpoint masses are m_i=t_i(Wt)_i. Intensity is Var_m(share)/(rho_m(1-rho_m));
    layout is the pair-weighted covariance divided by that variance. Their product equals
    2*Capy-1. Exposure and isolation instead average local shares with Y and X populations.

    Args:
        shares (np.ndarray): Length-256 group shares in [0, 1], in row-major order.
        total_population (np.ndarray): Aligned positive population masses.

    Returns:
        FactorizationScores: Typed factors plus comparison metrics, including capy_phi,
            x_isolation, and y_to_x_exposure. No input is mutated.

    Raises:
        ValueError: Inputs are invalid, factor variance is zero, or factorization fails.
    """
    adjacency = build_grid_adjacency(GRID_SIDE_LENGTH)
    closed_adjacency = adjacency + sparse.eye_array(GRID_NODE_COUNT, format="csr")
    group_population = shares * total_population
    other_population = total_population - group_population
    scores = calculate_experiment_scores(adjacency, group_population, other_population)

    neighbor_totals = closed_adjacency @ total_population
    endpoint_mass = total_population * neighbor_totals
    total_endpoint_mass = endpoint_mass.sum()
    endpoint_share = float(endpoint_mass @ shares / total_endpoint_mass)
    deviations = shares - endpoint_share
    variance = float(endpoint_mass @ deviations**2 / total_endpoint_mass)

    if variance <= 0 or not 0 < endpoint_share < 1:
        raise ValueError("Capy factors require nonconstant shares and both groups")

    covariance = float(
        (total_population * deviations)
        @ (closed_adjacency @ (total_population * deviations))
        / total_endpoint_mass
    )
    intensity = variance / (endpoint_share * (1 - endpoint_share))
    layout = covariance / variance
    capy_phi = 2 * float(scores.metric_values["capy"]) - 1

    if not np.isclose(capy_phi, intensity * layout, rtol=0, atol=1e-8):
        raise ValueError("Capy does not match its intensity–layout factorization")

    local_shares = (closed_adjacency @ group_population) / neighbor_totals
    scores.metric_values.update(
        capy_phi=capy_phi,
        x_isolation=float(group_population @ local_shares / group_population.sum()),
        y_to_x_exposure=float(other_population @ local_shares / other_population.sum()),
    )

    return FactorizationScores(
        endpoint_share=endpoint_share, intensity=intensity, layout=layout, comparison_scores=scores
    )


def select_factorization_examples(scores_df: pd.DataFrame) -> list[SelectedExample]:
    """Select ten nearest grids per quadrant/share target, retaining repeats across targets.

    Candidates must lie within 0.04 of a target population share. Distance sums squared intensity
    differences and squared layout differences divided by 1.6². Seed breaks ties. Rank one
    supplies the example-grid strip.
    Small runs retain all available candidates; an empty target band raises ValueError.

    Args:
        scores_df (pd.DataFrame): One row per seed with group_share, intensity, and layout.
            The table is read without modification.

    Returns:
        list[SelectedExample]: Selections in quadrant, share-target, then rank order.

    Raises:
        ValueError: A share target has no candidates within 0.04.
        KeyError: A required score column is missing.
    """
    selections = []

    for quadrant, (intensity, layout) in QUADRANT_CENTERS.items():
        for target_share in EXAMPLE_SHARE_TARGETS:
            candidates_df = scores_df.loc[
                (scores_df["group_share"] - target_share).abs().le(0.04)
            ].copy()

            if candidates_df.empty:
                raise ValueError(
                    f"No accepted grids within 0.04 of population share {target_share}"
                )

            candidates_df["distance_squared"] = (candidates_df["intensity"] - intensity) ** 2 + (
                (candidates_df["layout"] - layout) / 1.6
            ) ** 2
            nearest_df = candidates_df.sort_values(["distance_squared", "seed"]).head(10)

            for rank, seed in enumerate(nearest_df["seed"], start=1):
                selections.append(
                    SelectedExample(
                        quadrant=quadrant,
                        target_group_share=target_share,
                        rank=rank,
                        seed=int(seed),
                    )
                )

    return selections
