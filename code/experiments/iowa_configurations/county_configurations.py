"""Compute population arrangements and segregation scores on Iowa county adjacency."""

import random
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from capy_metrics import MoranWeightType, build_moran_weights, capy, morans_I, relative_diversity
from national_pipeline.build_graphs.construct_graph import build_connected_graph
from national_pipeline.derived_file_paths import (
    build_join_output_paths,
    build_population_output_path,
)
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import PipelineConfig
from national_pipeline.population_table_columns import GeographyColumn, PopulationColumn
from scipy import sparse
from tqdm import trange


# The n-th county added to a cluster gets first-group share decay**n; 1.0 keeps whole counties.
CLUSTERED_DECAY = 0.98
MULTICLUSTER_DECAY = 0.95
WHOLE_COUNTY_SHARE = 0.8
# Fraction of the target first-group population spread over all counties by total population,
# giving every county share BACKGROUND_FRACTION * target_share before arrangement selection.
BACKGROUND_FRACTION = 0.1
# Add share noise after arrangement and background; half-width is a share of each county's TOTPOP.
RANDOMIZE = True
NOISE_HALF_WIDTH = 0.05
# Stream tags keep noise seeds distinct; NumPy treats trailing zeros in seed lists as absent.
NOISE_STREAM = 0
MAP_NOISE_STREAM = 1


class CountyArrangement(StrEnum):
    """Spatial patterns of first-group counties; cluster families use decaying partial shares."""

    ISOLATED = "isolated"
    CLUSTERED = "clustered"
    MULTICLUSTER = "multicluster"
    RANDOM = "random"


@dataclass(frozen=True)
class ScoredCountyConfiguration:
    """Numeric scores and component count for an achieved county arrangement.

    Undefined metrics raise during computation, so this record contains only numeric scores.
    """

    component_count: int
    group_share: float
    metric_values: dict[str, float]


@dataclass(frozen=True)
class CountyConfigurationResult:
    """One sampling attempt; configuration is absent when no multicluster sample was found."""

    arrangement: CountyArrangement
    sample: int
    seed: int
    target_share: float
    configuration: ScoredCountyConfiguration | None

    def to_record(self) -> dict[str, float | str | None]:
        """Flatten an attempt and its available scores into the county-results table."""
        record = {
            "arrangement": self.arrangement.value,
            "sample": self.sample,
            "seed": self.seed,
            "target_share": self.target_share,
            "status": "no_multicluster_sample",
        }

        if self.configuration is not None:
            record.update(
                status="ready",
                group_share=self.configuration.group_share,
                component_count=self.configuration.component_count,
                **self.configuration.metric_values,
            )

        return record


def grow_county_cluster(
    graph: nx.Graph,
    selected_shares: dict[str, float],
    target_population: float,
    rng: random.Random,
    decay: float,
) -> dict[str, float]:
    """Add a randomized connected expansion whose decayed first-group population reaches target.

    The n-th county added in this call, counting from one, gets first-group share decay**n and
    contributes that share of its population toward the target. Existing selected counties are
    excluded from growth. The final county can overshoot the target. The inputs are unchanged;
    only the supplied rng advances.

    Args:
        graph (nx.Graph): County adjacency with string IDs and positive TOTPOP counts.
        selected_shares (dict[str, float]): First-group shares of counties already assigned.
        target_population (float): Additional first-group population sought in this expansion.
        rng (random.Random): Experiment-owned random stream for seed and frontier choices.
        decay (float): Per-step share multiplier in (0, 1]; 1.0 assigns whole counties.

    Returns:
        dict[str, float]: Existing shares plus the newly grown component's shares. Growth can stop
            below the target if its remaining connected region is exhausted. No available nodes
            returns a copy of the existing shares.

    Raises:
        KeyError: A county lacks its total-population attribute.
    """
    available_counties = sorted(set(graph) - set(selected_shares))

    if not available_counties:
        return dict(selected_shares)

    frontier = [rng.choice(available_counties)]
    added_shares: dict[str, float] = {}
    added_population = 0.0

    while frontier and added_population < target_population:
        rng.shuffle(frontier)
        county_id = frontier.pop(0)

        if county_id in selected_shares or county_id in added_shares:
            continue

        share = decay ** (len(added_shares) + 1)
        added_shares[county_id] = share
        added_population += share * graph.nodes[county_id][PopulationColumn.TOTAL]
        frontier.extend(
            sorted(set(graph.neighbors(county_id)) - set(added_shares) - set(selected_shares))
        )

    return selected_shares | added_shares


def select_county_arrangement(
    graph: nx.Graph,
    target_share: float,
    arrangement: CountyArrangement,
    rng: random.Random,
) -> dict[str, float] | None:
    """Choose random counties, a greedy independent set, or decaying connected county clusters.

    Selection places the target's non-background part: (1 - BACKGROUND_FRACTION) of the target
    first-group population, drawn from population left after the uniform background share. Returned
    shares apply to that remaining population; calculate_first_shares() adds the background.
    Random and isolated counties get share WHOLE_COUNTY_SHARE. Cluster families give the n-th
    county added to each cluster share CLUSTERED_DECAY**n or MULTICLUSTER_DECAY**n, restarting n
    for each multicluster seed. Independent sets and decaying clusters can exhaust their eligible
    nodes before the target; cluster growth can overshoot. Multicluster attempts grow four seeds in
    sequence, each toward a quarter of the arrangement target, and retry up to 100 times, returning
    None if none retain 2–4 components.
    Random arrangements take counties in shuffled order until the target is reached or exceeded,
    without an adjacency constraint; they are not uniform draws from all feasible subsets.

    Args:
        graph (nx.Graph): Connected county graph with string IDs and positive TOTPOP counts.
        target_share (float): Requested share of total county population, strictly between 0 and 1.
        arrangement (CountyArrangement): RANDOM, ISOLATED, CLUSTERED, or MULTICLUSTER selection.
        rng (random.Random): Experiment-owned random stream, advanced by the selection.

    Returns:
        dict[str, float] | None: Share of each selected county's post-background population
            assigned to the first group; unlisted counties have share zero. Keys are exactly the
            arrangement's selected counties. None after unsuccessful multicluster attempts.

    Raises:
        ValueError: The target share is outside the open interval (0, 1).
        KeyError: A county lacks its total-population attribute.
    """
    if not 0 < target_share < 1:
        raise ValueError("Target share must lie strictly between zero and one")

    target_population = target_share * sum(
        county_attributes[PopulationColumn.TOTAL] for county_attributes in graph.nodes.values()
    )
    # Shares s of post-background population add s * (1 - background) * TOTPOP first-group people.
    background_share = BACKGROUND_FRACTION * target_share
    target_population *= (1 - BACKGROUND_FRACTION) / (1 - background_share)

    if arrangement == CountyArrangement.CLUSTERED:
        return grow_county_cluster(graph, {}, target_population, rng, CLUSTERED_DECAY)

    if arrangement == CountyArrangement.MULTICLUSTER:
        for _ in range(100):
            selected_shares: dict[str, float] = {}

            for _ in range(4):
                selected_shares = grow_county_cluster(
                    graph, selected_shares, target_population / 4, rng, MULTICLUSTER_DECAY
                )

            if 2 <= nx.number_connected_components(graph.subgraph(selected_shares)) <= 4:
                return selected_shares

        return None

    selected_counties: set[str] = set()
    excluded_counties: set[str] = set()
    county_ids = sorted(graph)
    rng.shuffle(county_ids)
    selected_population = 0

    for county_id in county_ids:
        if county_id in excluded_counties:
            continue

        selected_counties.add(county_id)

        if arrangement == CountyArrangement.ISOLATED:
            excluded_counties |= {county_id, *graph.neighbors(county_id)}

        selected_population += WHOLE_COUNTY_SHARE * graph.nodes[county_id][PopulationColumn.TOTAL]

        if selected_population >= target_population:
            break

    return {county_id: WHOLE_COUNTY_SHARE for county_id in selected_counties}


def calculate_first_shares(
    selected_shares: dict[str, float], county_ids: Iterable[str], target_share: float
) -> np.ndarray:
    """Combine the uniform background share with an arrangement's post-background shares.

    Every county first gets share BACKGROUND_FRACTION * target_share. A selected county's
    arrangement share then applies to its remaining population, so its total first-group share is
    background + (1 - background) * selected share.

    Args:
        selected_shares (dict[str, float]): Arrangement shares from select_county_arrangement().
        county_ids (Iterable[str]): County order for the returned shares.
        target_share (float): Requested first-group population share that set the background.

    Returns:
        np.ndarray: Total first-group share of each county, in county_ids order.
    """
    background_share = BACKGROUND_FRACTION * target_share
    arrangement_shares = np.array(
        [selected_shares.get(county_id, 0.0) for county_id in county_ids]
    )

    return background_share + (1 - background_share) * arrangement_shares

def perturb_first_shares(first_shares: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Add symmetric uniform share noise, narrowed near 0 and 1 so shares stay in [0, 1].

    Each county's half-width is min(NOISE_HALF_WIDTH, share, 1 - share), so the expected share is
    unchanged and no county gets negative or excess first-group population.

    Args:
        first_shares (np.ndarray): Total first-group shares in [0, 1].
        rng (np.random.Generator): Noise stream, kept separate from county selection.

    Returns:
        np.ndarray: Perturbed shares in [0, 1], in the input order.
    """
    half_widths = np.minimum(NOISE_HALF_WIDTH, np.minimum(first_shares, 1 - first_shares))
    return first_shares + rng.uniform(-half_widths, half_widths)


def sample_county_configurations(
    graph: nx.Graph,
    arrangement: CountyArrangement,
    target_shares: np.ndarray,
    samples_per_share: int,
    seed: int,
) -> list[CountyConfigurationResult]:
    """Sample whole-county assignments and score their achieved population shares.

    A random stream seeded with seed + sample advances across target shares in their supplied
    order. Each share gets a fresh county selection, not an extension of the preceding selection.
    Scores use quadratic Capy and row-standardized Moran on the same adjacency.

    Args:
        graph (nx.Graph): Connected county graph with string IDs and positive TOTPOP counts.
        arrangement (CountyArrangement): Constraint on the first-group counties.
        target_shares (np.ndarray): Requested population shares in sampling order, each in (0, 1).
        samples_per_share (int): Positive number of attempts at each target share.
        seed (int): Base random seed, incremented for each sample.

    Returns:
        list[CountyConfigurationResult]: Attempts in sample, then target-share order.

    Raises:
        ValueError: A target share or metric input is invalid.
        KeyError: A county lacks its total population.
    """
    county_ids = sorted(graph)
    county_populations = np.array(
        [graph.nodes[county_id][PopulationColumn.TOTAL] for county_id in county_ids]
    )
    adjacency = nx.to_scipy_sparse_array(graph, nodelist=county_ids, format="csr")
    moran_with_self_weights = build_moran_weights(adjacency, MoranWeightType.WITH_SELF)
    moran_row_standardized_weights = build_moran_weights(
        adjacency, MoranWeightType.ROW_STANDARDIZED
    )

    results: list[CountyConfigurationResult] = []

    for sample in trange(samples_per_share, desc=arrangement.value, disable=None):
        rng = random.Random(seed + sample)
        noise_rng = np.random.default_rng([seed, NOISE_STREAM, sample])


        for target_share in target_shares:
            selected_shares = select_county_arrangement(graph, target_share, arrangement, rng)
            configuration = None

            if selected_shares is not None:
                first_shares = calculate_first_shares(selected_shares, county_ids, target_share)

                if RANDOMIZE:
                    first_shares = perturb_first_shares(first_shares, noise_rng)


                first_population = county_populations * first_shares
                second_population = county_populations - first_population
                _, intensity, layout = calculate_capy_factors(adjacency, first_population, county_populations)
                aspatial_r = relative_diversity(first_population, county_populations)
                moran_with_self = morans_I(moran_with_self_weights, first_shares)

                configuration = ScoredCountyConfiguration(
                    component_count=nx.number_connected_components(
                        graph.subgraph(selected_shares)
                    ),
                    group_share=float(first_population.sum() / county_populations.sum()),
                    metric_values={
                        "capy": capy(adjacency, first_population, second_population),
                        "moran_row_standardized": morans_I(
                            moran_row_standardized_weights, first_shares
                        ),
                        "intensity": intensity,
                        "layout": layout,
                        "relative_diversity": aspatial_r,
                        "moran_with_self": moran_with_self,
                        "intensity_minus_relative_diversity": intensity - aspatial_r,
                        "layout_minus_moran_with_self": layout - moran_with_self,
                    },
                )

            results.append(
                CountyConfigurationResult(
                    arrangement=arrangement,
                    sample=sample,
                    seed=seed + sample,
                    target_share=float(target_share),
                    configuration=configuration,
                )
            )

    return results


def run_iowa_experiments(
    config: PipelineConfig,
    repository_root: Path,
    data_directory: Path,
    samples_per_share: int = 500,
    share_count: int = 100,
    seed: int = 42,
) -> None:
    """Save county arrangements, their scores, and map examples.

    Reads the joined 2020 Iowa counties. Scores are quadratic Capy and row-standardized Moran. A
    separate target-0.3 example per arrangement is retained for the map.

    Args:
        config (PipelineConfig): Supplies the joined-geography root. Year, state, and level are
            fixed to 2020 Iowa counties regardless of the configured national selections.
        repository_root (Path): Base for the configured joined-geography directory.
        data_directory (Path): Destination for iowa_scores.parquet, iowa_examples.parquet, and
            iowa_edges.parquet. Saved edges preserve the adjacency used for scoring and drawing.
        samples_per_share (int): Positive number of attempts at each target share. Default: 500.
        share_count (int): At least two evenly spaced target shares per family. Default: 100.
        seed (int): Base random seed, incremented by sample; the map uses this seed. Default: 42.

    Raises:
        OSError: Joined counties cannot be read or experiment outputs cannot be written.
        ValueError: Sample settings are invalid, graph construction does not retain all 99
            counties, no multicluster map example is found, or a metric input is invalid.
    """
    if samples_per_share < 1 or share_count < 2:
        raise ValueError("Use positive samples per share and at least two target shares")

    population_path = build_population_output_path(2020, GeographyLevel.COUNTY, "19")
    geography_path = build_join_output_paths(population_path)[0]
    counties_df = gpd.read_parquet(
        repository_root / config.joined_geography_directory / geography_path
    )
    graph, removed_counties_df = build_connected_graph(counties_df, warn_on_polygon_overlaps=False)

    if len(graph) != 99 or not removed_counties_df.empty:
        raise ValueError("The Iowa experiment requires all 99 counties")

    results: list[CountyConfigurationResult] = []
    example_tables = []

    for arrangement in CountyArrangement:
        minimum_target_share = 0.01 if arrangement == CountyArrangement.ISOLATED else 0.001
        target_shares = np.linspace(minimum_target_share, 0.5, share_count)
        results.extend(
            sample_county_configurations(graph, arrangement, target_shares, samples_per_share, seed)
        )

        selected_shares = select_county_arrangement(graph, 0.3, arrangement, random.Random(seed))

        if selected_shares is None:
            raise ValueError("No multicluster map example; choose another seed")

        geographic_ids = counties_df[GeographyColumn.GEOGRAPHIC_ID]
        first_share = calculate_first_shares(selected_shares, geographic_ids, 0.3)

        if RANDOMIZE:
            first_share = perturb_first_shares(
                first_share, np.random.default_rng([seed, MAP_NOISE_STREAM])
            )

        example_tables.append(
            counties_df.assign(
                arrangement=arrangement.value,
                first_group=geographic_ids.isin(sorted(selected_shares)),
                first_share=first_share,
            )
        )


    scores_df = pd.DataFrame([result.to_record() for result in results]).assign(
        randomized=RANDOMIZE
    )
    examples_df = gpd.GeoDataFrame(pd.concat(example_tables), crs=counties_df.crs)
    edges_df = pd.DataFrame(
        sorted(tuple(sorted(edge)) for edge in graph.edges), columns=pd.Index(["source", "target"])
    )

    data_directory.mkdir(parents=True, exist_ok=True)
    scores_df.to_parquet(data_directory / "iowa_scores.parquet", index=False)
    examples_df.to_parquet(data_directory / "iowa_examples.parquet", index=False)
    edges_df.to_parquet(data_directory / "iowa_edges.parquet", index=False)

def calculate_capy_factors(
    adjacency: sparse.csr_array, group_population: np.ndarray, total_population: np.ndarray
) -> tuple[float, float, float]:
    closed_adjacency = adjacency + sparse.eye_array(len(total_population), format="csr")
    shares = group_population / total_population
    endpoint_mass = total_population * (closed_adjacency @ total_population)
    endpoint_share = endpoint_mass @ shares / endpoint_mass.sum()
    deviations = shares - endpoint_share
    variance = endpoint_mass @ deviations**2 / endpoint_mass.sum()
    covariance = (
        (total_population * deviations)
        @ (closed_adjacency @ (total_population * deviations))
        / endpoint_mass.sum()
    )
    return float(endpoint_share), float(variance / (endpoint_share * (1 - endpoint_share))), float(covariance / variance)
