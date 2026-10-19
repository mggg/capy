"""Compute and save observed dispersion experiment results."""

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from national_pipeline.geography_types import StudyAreaType
from national_pipeline.pipeline_config import PipelineConfig
from national_pipeline.population_table_columns import PopulationColumn
from shapely import MultiPolygon, Polygon, union_all

from experiments.experiment_scores import ExperimentScores, calculate_experiment_scores
from experiments.neighborhood_change.load_city_tracts import CityTracts, read_city_tracts


@dataclass(frozen=True)
class NeighborhoodDefinition:
    """A named 2020 core identified by component rank and a required reference tract.

    component_rank is zero-based, with the largest above-mean Black-share component first.
    """

    name: str
    component_rank: int
    reference_tract_id: str


@dataclass(frozen=True)
class CityDefinition:
    """Census place and state codes with the neighborhoods selected from that city's graph."""

    name: str
    place_id: str
    state_code: str
    neighborhoods: tuple[NeighborhoodDefinition, ...]


CITIES = (
    CityDefinition(
        name="chicago",
        place_id="1714000",
        state_code="17",
        neighborhoods=(
            NeighborhoodDefinition(
                name="south_side", component_rank=0, reference_tract_id="17031691200"
            ),
            NeighborhoodDefinition(
                name="austin", component_rank=1, reference_tract_id="17031831400"
            ),
        ),
    ),
    CityDefinition(
        name="philadelphia",
        place_id="4260000",
        state_code="42",
        neighborhoods=(
            NeighborhoodDefinition(
                name="germantown", component_rank=0, reference_tract_id="42101028000"
            ),
            NeighborhoodDefinition(
                name="west_philadelphia", component_rank=1, reference_tract_id="42101008200"
            ),
        ),
    ),
)


@dataclass(frozen=True)
class NeighborhoodResults:
    """Scores, tract memberships, plotting geometry, and the fixed 2020 core for a neighborhood.

    Scores and memberships include every buffer; maps contain only the selected plotting buffer.
    """

    scores_df: pd.DataFrame
    memberships_df: pd.DataFrame
    maps_df: gpd.GeoDataFrame
    cores_df: gpd.GeoDataFrame


@dataclass(frozen=True)
class ClusterSummary:
    """Scores, Black population, and spread about a fixed population medoid.

    Mean Black distance is the population-weighted mean graph-hop distance to the medoid.
    Unit count is the number of selected tracts.
    """

    scores: ExperimentScores
    black_population: int
    medoid: str
    mean_black_distance: float
    unit_count: int

    def to_record(self) -> dict[str, float | str | None]:
        """Flatten cluster scores and population accounting into table columns."""
        return {
            **self.scores.to_record(),
            "black_population": self.black_population,
            "medoid": self.medoid,
            "mean_black_distance": self.mean_black_distance,
            "unit_count": self.unit_count,
        }


@dataclass(frozen=True)
class ClusterResult:
    """One neighborhood's summary at a census year and graph-hop buffer."""

    cluster: str
    year: int
    buffer_steps: int
    summary: ClusterSummary

    def to_record(self) -> dict[str, float | str | None]:
        """Flatten the neighborhood identity and its summary into one result row."""
        return {
            "cluster": self.cluster,
            "year": self.year,
            "buffer_steps": self.buffer_steps,
            **self.summary.to_record(),
        }


def select_black_clusters(graph: nx.Graph) -> list[set[str]]:
    """Select the two largest components above the unweighted mean Black tract share.

    Components are ranked by tract count, then their sorted node IDs. The connected city graph,
    including artificial connections, defines adjacency.

    Args:
        graph (nx.Graph): Connected undirected city graph with string tract IDs and BLACK/WHITE
            counts. Each tract must have positive combined population.

    Returns:
        list[set[str]]: The two selected components, largest first.

    Raises:
        ValueError: Fewer than two components satisfy the threshold.
        KeyError: A required population attribute is absent.
    """
    black_shares = {
        tract_id: population_counts[PopulationColumn.NON_HISPANIC_BLACK]
        / (
            population_counts[PopulationColumn.NON_HISPANIC_BLACK]
            + population_counts[PopulationColumn.NON_HISPANIC_WHITE]
        )
        for tract_id, population_counts in graph.nodes.items()
    }
    mean_black_share = np.mean(list(black_shares.values()))
    above_mean_tract_ids = [
        tract_id for tract_id, share in black_shares.items() if share > mean_black_share
    ]
    black_components = sorted(
        nx.connected_components(graph.subgraph(above_mean_tract_ids)),
        key=lambda tract_ids: (-len(tract_ids), sorted(tract_ids)),
    )

    if len(black_components) < 2:
        raise ValueError("Expected two separate above-mean Black tract clusters")

    return black_components[:2]


def fill_cluster_holes(polygons: gpd.GeoSeries) -> Polygon | MultiPolygon:
    """Dissolve selected polygons and fill interior rings, preserving separate exterior parts.

    Args:
        polygons (gpd.GeoSeries): Selected tract polygons in one coordinate system.

    Returns:
        Polygon | MultiPolygon: Their union with holes filled.

    Raises:
        ValueError: The union is empty or either union operation produces a nonpolygonal result.
    """
    cluster_union = union_all(polygons.to_numpy())

    if not isinstance(cluster_union, (Polygon, MultiPolygon)) or cluster_union.is_empty:
        raise ValueError("Cluster polygons must have a nonempty polygonal union")

    polygon_parts = (
        [cluster_union] if isinstance(cluster_union, Polygon) else list(cluster_union.geoms)
    )
    filled_union = union_all([Polygon(part.exterior) for part in polygon_parts])

    if not isinstance(filled_union, (Polygon, MultiPolygon)) or filled_union.is_empty:
        raise ValueError("Filled cluster must remain nonempty and polygonal")

    return filled_union


def select_overlapping_tracts(
    tracts_df: gpd.GeoDataFrame,
    cluster_shape: Polygon | MultiPolygon,
) -> gpd.GeoDataFrame:
    """Select whole tracts with strictly more than half their area inside a same-CRS cluster.

    Args:
        tracts_df (gpd.GeoDataFrame): Tracts with valid, positive-area polygons in a projected CRS.
        cluster_shape (Polygon | MultiPolygon): Selection shape in that CRS. CRS agreement is
            a caller requirement because the shape does not carry a CRS.

    Returns:
        gpd.GeoDataFrame: Independent table retaining full tract geometry and counts. Geometries
            are neither clipped nor population-weighted.
    """
    area_fractions = tracts_df.geometry.intersection(cluster_shape).area / tracts_df.geometry.area

    return tracts_df.loc[area_fractions.gt(0.5)].copy()


def find_black_population_medoid(graph: nx.Graph, core_tract_ids: list[str]) -> str:
    """Minimize Black-weighted path length among core nodes, using full-city shortest paths.

    Candidate and destination nodes both belong to the historical buffer-zero selection.
    Shortest paths may leave that selection. Equal objectives use the smallest geographic ID.

    Args:
        graph (nx.Graph): Connected city graph with BLACK counts and string geographic IDs.
        core_tract_ids (list[str]): Nonempty selection of graph nodes used as candidates and
            destinations.

    Returns:
        str: Geographic ID minimizing population-weighted edge-count distance to the core.

    Raises:
        ValueError: The core selection is empty.
        KeyError: A population attribute or a path to a selected destination is absent.
        nx.NodeNotFound: A candidate does not belong to the graph.
    """
    if not core_tract_ids:
        raise ValueError("A historical cluster needs at least one core tract")

    candidate_distances = []

    for tract_id in sorted(core_tract_ids):
        distances = nx.single_source_shortest_path_length(graph, tract_id)
        weighted_distance = sum(
            graph.nodes[destination_id][PopulationColumn.NON_HISPANIC_BLACK]
            * distances[destination_id]
            for destination_id in core_tract_ids
        )
        candidate_distances.append((weighted_distance, tract_id))

    return min(candidate_distances)[1]


def summarize_cluster(
    graph: nx.Graph,
    selected_tracts_df: gpd.GeoDataFrame,
    medoid: str,
) -> tuple[ClusterSummary, gpd.GeoDataFrame]:
    """Calculate cluster scores, mass, spread, and radial positions around a fixed core medoid.

    Metric adjacency is the selected induced subgraph, while distances use the full city graph.
    Radial direction comes from projected centroids; radius is unweighted shortest-path length.
    Undefined metrics retain their reasons. Positive selected Black population is required
    for the mean distance and is a caller precondition.

    Args:
        graph (nx.Graph): Connected city graph with projected centroid_x/centroid_y attributes.
        selected_tracts_df (gpd.GeoDataFrame): Nonempty tract selection indexed by graph node ID, with
            BLACK and WHITE counts and positive combined population at every tract.
        medoid (str): Fixed core-center node in the city graph.

    Returns:
        tuple[ClusterSummary, gpd.GeoDataFrame]: Scores and population/distance
            accounting, plus a copied tract table with radial_x, radial_y, black_share, and
            is_medoid columns.

    Raises:
        ValueError: Population or metric inputs are invalid.
        KeyError: An attribute or path to a selected node is absent.
        nx.NetworkXError: The selection is empty or contains nodes outside the city graph.
        nx.NodeNotFound: The medoid is absent from the city graph.
    """
    selected_tracts_df = selected_tracts_df.copy()
    tract_ids = selected_tracts_df.index.tolist()
    adjacency = nx.to_scipy_sparse_array(
        graph.subgraph(tract_ids), nodelist=tract_ids, format="csr"
    )
    black_population = selected_tracts_df[PopulationColumn.NON_HISPANIC_BLACK].to_numpy()
    white_population = selected_tracts_df[PopulationColumn.NON_HISPANIC_WHITE].to_numpy()
    scores = calculate_experiment_scores(adjacency, black_population, white_population)

    distances = nx.single_source_shortest_path_length(graph, medoid)
    graph_distances = np.array([distances[tract_id] for tract_id in tract_ids])
    medoid_attributes = graph.nodes[medoid]
    centroid_angles = np.array(
        [
            np.arctan2(
                graph.nodes[tract_id]["centroid_y"] - medoid_attributes["centroid_y"],
                graph.nodes[tract_id]["centroid_x"] - medoid_attributes["centroid_x"],
            )
            for tract_id in tract_ids
        ]
    )
    selected_tracts_df["radial_x"] = graph_distances * np.cos(centroid_angles)
    selected_tracts_df["radial_y"] = graph_distances * np.sin(centroid_angles)
    selected_tracts_df["black_share"] = black_population / (black_population + white_population)
    selected_tracts_df["is_medoid"] = selected_tracts_df.index == medoid

    summary = ClusterSummary(
        scores=scores,
        black_population=int(black_population.sum()),
        medoid=medoid,
        mean_black_distance=float(black_population @ graph_distances / black_population.sum()),
        unit_count=len(selected_tracts_df),
    )

    return summary, selected_tracts_df


def run_observed_dispersion(
    config: PipelineConfig,
    repository_root: Path,
    data_directory: Path,
    buffer_steps: int = 3,
) -> None:
    """Save 0–10-hop memberships and summaries, plus geometry for one selected plotting buffer.

    Historical tracts use full source geometry, not city-clipped shapes. The same connected city
    graph supplies cluster expansion, medoids, paths, and induced-subgraph metric adjacency.
    Selected component ranks retain their neighborhood names. Each selected 2020 core
    must contain its reference tract, the medoid of the corresponding named 2020 neighborhood,
    so changes in component rank cannot silently exchange the names.

    Args:
        config (PipelineConfig): Maximum-city configuration with definition vintage 2020 and
            completed tract inputs for 1980, 1990, 2000, 2010, and 2020.
        repository_root (Path): Base for relative configured input directories.
        data_directory (Path): Destination for cluster_scores, cluster_memberships,
            cluster_maps, and cluster_cores Parquets.
        buffer_steps (int): Buffer retained for maps, from 0 to 10. Default: 3. Score and
            membership tables retain every buffer regardless of this choice.

    Raises:
        OSError: An input cannot be read or an output cannot be written.
        ValueError: Configuration, graph/polygon agreement, cluster selection, or metric input
            is invalid.
    """
    if config.study_area_type != StudyAreaType.MAX_CITY or config.study_area_vintage != 2020:
        raise ValueError("Observed dispersion requires the 2020 maximum-city configuration")

    if not 0 <= buffer_steps <= 10:
        raise ValueError("Plotting buffer must be between zero and ten graph steps")

    neighborhood_results: list[NeighborhoodResults] = []

    for city in CITIES:
        city_tracts_by_year = {
            year: read_city_tracts(config, repository_root, city.place_id, city.state_code, year)
            for year in (1980, 1990, 2000, 2010, 2020)
        }
        neighborhood_results.extend(
            analyze_city_neighborhoods(city, city_tracts_by_year, buffer_steps)
        )

    scores_df = pd.concat([result.scores_df for result in neighborhood_results], ignore_index=True)
    memberships_df = pd.concat(
        [result.memberships_df for result in neighborhood_results], ignore_index=True
    )
    maps_df = gpd.GeoDataFrame(
        pd.concat([result.maps_df for result in neighborhood_results], ignore_index=True),
        crs="ESRI:102003",
    )
    cores_df = gpd.GeoDataFrame(
        pd.concat([result.cores_df for result in neighborhood_results], ignore_index=True),
        crs="ESRI:102003",
    )

    data_directory.mkdir(parents=True, exist_ok=True)
    scores_df.to_parquet(data_directory / "cluster_scores.parquet", index=False)
    memberships_df.to_parquet(data_directory / "cluster_memberships.parquet", index=False)
    maps_df.to_parquet(data_directory / "cluster_maps.parquet", index=False)
    cores_df.to_parquet(data_directory / "cluster_cores.parquet", index=False)


def analyze_city_neighborhoods(
    city: CityDefinition,
    city_tracts_by_year: dict[int, CityTracts],
    map_buffer_steps: int,
) -> list[NeighborhoodResults]:
    """Identify named 2020 cores and measure their buffered regions in each census year.

    Args:
        city (CityDefinition): Component ranks and reference tracts for the named neighborhoods.
        city_tracts_by_year (dict[int, CityTracts]): Matching graphs and polygons, including 2020.
        map_buffer_steps (int): Buffer whose tract geometry is retained for plotting, from 0 to 10.

    Returns:
        list[NeighborhoodResults]: One set of tables per neighborhood, in definition order.

    Raises:
        ValueError: A ranked core lacks its reference tract, a selection is empty, or scores
            cannot be computed from the supplied populations.
        KeyError: The 2020 inputs or required graph attributes are missing.
    """
    city_2020 = city_tracts_by_year[2020]
    black_components = select_black_clusters(city_2020.graph)
    neighborhood_results = []

    for neighborhood in city.neighborhoods:
        core_tract_ids = black_components[neighborhood.component_rank]

        if neighborhood.reference_tract_id not in core_tract_ids:
            raise ValueError(
                f"The selected {city.name} {neighborhood.name} core lacks reference tract "
                f"{neighborhood.reference_tract_id}; inspect the 2020 cluster identities"
            )

        cluster_id = f"{city.name}_{neighborhood.name}"
        buffer_shapes = build_buffer_shapes(city_2020.graph, city_2020.tracts_df, core_tract_ids)
        neighborhood_results.append(
            analyze_cluster_years(city_tracts_by_year, buffer_shapes, cluster_id, map_buffer_steps)
        )

    return neighborhood_results


def build_buffer_shapes(
    graph: nx.Graph,
    tracts_df: gpd.GeoDataFrame,
    core_tract_ids: set[str],
) -> list[Polygon | MultiPolygon]:
    """Dissolve and fill the core and its first ten graph-hop expansions.

    Args:
        graph (nx.Graph): City adjacency, including any artificial component connections.
        tracts_df (gpd.GeoDataFrame): Polygon table indexed by every graph node ID, in one CRS.
        core_tract_ids (set[str]): Nonempty initial component of graph nodes.

    Returns:
        list[Polygon | MultiPolygon]: Eleven shapes in buffer order, starting with the filled
            core. Expansion uses graph nodes before hole filling.

    Raises:
        KeyError: An expanded node lacks a polygon.
        ValueError: A polygon union is empty or nonpolygonal.
        nx.NetworkXError: A core node is absent from the graph.
    """
    expanded_tract_ids = set(core_tract_ids)
    buffer_shapes = []

    for _ in range(11):
        buffer_shapes.append(fill_cluster_holes(tracts_df.loc[sorted(expanded_tract_ids)].geometry))
        expanded_tract_ids |= {
            neighbor for tract_id in expanded_tract_ids for neighbor in graph.neighbors(tract_id)
        }

    return buffer_shapes


def analyze_cluster_years(
    city_tracts_by_year: dict[int, CityTracts],
    buffer_shapes: list[Polygon | MultiPolygon],
    cluster_id: str,
    map_buffer_steps: int,
) -> NeighborhoodResults:
    """Select and score historical tracts while holding each year's core medoid fixed.

    Every year, including 2020, selects tracts with strictly more than half their full area inside
    each buffer shape. The zero-buffer selection fixes that year's medoid for all larger buffers.

    Args:
        city_tracts_by_year (dict[int, CityTracts]): Matching city graphs and tract tables in
            ESRI:102003, in the desired census-year order.
        buffer_shapes (list[Polygon | MultiPolygon]): Same-CRS shapes ordered from core outward.
            Each selection must contain tracts with positive combined Black and White population,
            and its total Black population must be positive.
        cluster_id (str): Neighborhood identifier added to every table.
        map_buffer_steps (int): Valid index of the buffer whose geometry is retained for plotting.

    Returns:
        NeighborhoodResults: All year/buffer scores and memberships, one map per year, and the
            fixed 2020 core shape.

    Raises:
        ValueError: A year's core is empty or metric inputs are invalid.
        KeyError: Required attributes or paths are missing.
    """
    summaries: list[ClusterResult] = []
    membership_tables = []
    map_tables = []

    for year, city_tracts in city_tracts_by_year.items():
        core_tracts_df = select_overlapping_tracts(city_tracts.tracts_df, buffer_shapes[0])
        medoid = find_black_population_medoid(city_tracts.graph, core_tracts_df.index.tolist())

        for buffer_steps, buffer_shape in enumerate(buffer_shapes):
            selected_tracts_df = select_overlapping_tracts(city_tracts.tracts_df, buffer_shape)
            summary, map_df = summarize_cluster(city_tracts.graph, selected_tracts_df, medoid)
            summaries.append(
                ClusterResult(
                    cluster=cluster_id, year=year, buffer_steps=buffer_steps, summary=summary
                )
            )
            membership_tables.append(
                pd.DataFrame({"geographic_id": selected_tracts_df.index}).assign(
                    cluster=cluster_id, year=year, buffer_steps=buffer_steps
                )
            )

            if buffer_steps == map_buffer_steps:
                map_tables.append(
                    map_df.assign(cluster=cluster_id, year=year, buffer_steps=buffer_steps)
                )

    scores_df = pd.DataFrame([result.to_record() for result in summaries])
    memberships_df = pd.concat(membership_tables, ignore_index=True).reindex(
        columns=["cluster", "year", "buffer_steps", "geographic_id"]
    )
    maps_df = gpd.GeoDataFrame(pd.concat(map_tables), crs="ESRI:102003")
    cores_df = gpd.GeoDataFrame(
        {"cluster": [cluster_id], "geometry": [buffer_shapes[0]]}, crs="ESRI:102003"
    )

    return NeighborhoodResults(
        scores_df=scores_df, memberships_df=memberships_df, maps_df=maps_df, cores_df=cores_df
    )
