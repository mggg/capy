"""Compute population arrangements and segregation scores on Iowa county adjacency."""

import random
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from capy_metrics import MoranWeightType, build_moran_weights, capy, morans_I
from national_pipeline.build_graphs.construct_graph import build_connected_graph
from national_pipeline.derived_file_paths import (
    build_join_output_paths,
    build_population_output_path,
)
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import PipelineConfig
from national_pipeline.population_table_columns import GeographyColumn, PopulationColumn
from tqdm import trange


class CountyArrangement(StrEnum):
    """Constraints on the induced subgraph of entirely first-group counties."""

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
    selected_counties: set[str],
    target_population: float,
    rng: random.Random,
) -> set[str]:
    """Add a randomized connected expansion until its added population reaches the target.

    Existing selected nodes are excluded from growth. The final county can overshoot the target.
    The input set and graph are unchanged; only the supplied rng advances.

    Args:
        graph (nx.Graph): County adjacency with string IDs and positive TOTPOP counts.
        selected_counties (set[str]): Counties already assigned to the first group.
        target_population (float): Additional population sought in this expansion.
        rng (random.Random): Experiment-owned random stream for seed and frontier choices.

    Returns:
        set[str]: Existing selection plus the newly grown component. Growth can stop below the
            target if its remaining connected region is exhausted. No available nodes returns a
            copy of the existing selection.

    Raises:
        KeyError: A county lacks its total-population attribute.
    """
    available_counties = sorted(set(graph) - selected_counties)

    if not available_counties:
        return set(selected_counties)

    frontier = [rng.choice(available_counties)]
    added_counties = set()
    added_population = 0

    while frontier and added_population < target_population:
        rng.shuffle(frontier)
        county_id = frontier.pop(0)

        if county_id in selected_counties or county_id in added_counties:
            continue

        added_counties.add(county_id)
        added_population += graph.nodes[county_id][PopulationColumn.TOTAL]
        frontier.extend(
            sorted(set(graph.neighbors(county_id)) - added_counties - selected_counties)
        )

    return selected_counties | added_counties


def select_county_arrangement(
    graph: nx.Graph,
    target_share: float,
    arrangement: CountyArrangement,
    rng: random.Random,
) -> set[str] | None:
    """Choose random counties, a greedy independent set, or connected county clusters.

    Each county is assigned wholly to one group. Independent sets can exhaust their eligible
    nodes before the target; cluster growth can overshoot. Multicluster attempts split the target
    equally among four seeds and retry up to 50 times, returning None if none retain 2–4 components.
    Random arrangements take counties in shuffled order until the target is reached or exceeded,
    without an adjacency constraint; they are not uniform draws from all feasible subsets.

    Args:
        graph (nx.Graph): Connected county graph with string IDs and positive TOTPOP counts.
        target_share (float): Requested share of total county population, strictly between 0 and 1.
        arrangement (CountyArrangement): RANDOM, ISOLATED, CLUSTERED, or MULTICLUSTER selection.
        rng (random.Random): Experiment-owned random stream, advanced by the selection.

    Returns:
        set[str] | None: First-group county IDs, or None after unsuccessful multicluster attempts.

    Raises:
        ValueError: The target share is outside the open interval (0, 1).
        KeyError: A county lacks its total-population attribute.
    """
    if not 0 < target_share < 1:
        raise ValueError("Target share must lie strictly between zero and one")

    target_population = target_share * sum(
        county_attributes[PopulationColumn.TOTAL] for county_attributes in graph.nodes.values()
    )

    if arrangement == CountyArrangement.CLUSTERED:
        return grow_county_cluster(graph, set(), target_population, rng)

    if arrangement == CountyArrangement.MULTICLUSTER:
        for _ in range(50):
            selected_counties = set()

            for _ in range(4):
                selected_counties = grow_county_cluster(
                    graph, selected_counties, target_population / 4, rng
                )

            if 2 <= nx.number_connected_components(graph.subgraph(selected_counties)) <= 4:
                return selected_counties

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

        selected_population += graph.nodes[county_id][PopulationColumn.TOTAL]

        if selected_population >= target_population:
            break

    return selected_counties


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
    moran_weights = build_moran_weights(adjacency, MoranWeightType.ROW_STANDARDIZED)
    results: list[CountyConfigurationResult] = []

    for sample in trange(samples_per_share, desc=arrangement.value, disable=None):
        rng = random.Random(seed + sample)

        for target_share in target_shares:
            selected_counties = select_county_arrangement(graph, target_share, arrangement, rng)
            configuration = None

            if selected_counties is not None:
                first_population = county_populations * np.isin(
                    county_ids, sorted(selected_counties)
                )
                configuration = ScoredCountyConfiguration(
                    component_count=nx.number_connected_components(
                        graph.subgraph(selected_counties)
                    ),
                    group_share=float(first_population.sum() / county_populations.sum()),
                    metric_values={
                        "capy": capy(
                            adjacency, first_population, county_populations - first_population
                        ),
                        "moran_row_standardized": morans_I(
                            moran_weights, first_population / county_populations
                        ),
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

        selected_counties = select_county_arrangement(graph, 0.3, arrangement, random.Random(seed))

        if selected_counties is None:
            raise ValueError("No multicluster map example; choose another seed")

        example_tables.append(
            counties_df.assign(
                arrangement=arrangement.value,
                first_group=counties_df[GeographyColumn.GEOGRAPHIC_ID].isin(
                    sorted(selected_counties)
                ),
            )
        )

    scores_df = pd.DataFrame([result.to_record() for result in results])
    examples_df = gpd.GeoDataFrame(pd.concat(example_tables), crs=counties_df.crs)
    edges_df = pd.DataFrame(
        sorted(tuple(sorted(edge)) for edge in graph.edges), columns=pd.Index(["source", "target"])
    )

    data_directory.mkdir(parents=True, exist_ok=True)
    scores_df.to_parquet(data_directory / "iowa_scores.parquet", index=False)
    examples_df.to_parquet(data_directory / "iowa_examples.parquet", index=False)
    edges_df.to_parquet(data_directory / "iowa_edges.parquet", index=False)
