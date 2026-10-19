"""Load saved city tract graphs and their matching population polygons."""

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd
from national_pipeline.assign_study_areas.study_area_columns import StudyAreaColumn
from national_pipeline.build_graphs.archive_inventory import read_graph_selection_summary
from national_pipeline.build_graphs.graph_archives import read_graph_from_archive
from national_pipeline.derived_file_paths import (
    build_join_output_paths,
    build_population_output_path,
)
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import PipelineConfig
from national_pipeline.population_table_columns import GeographyColumn, PopulationColumn


@dataclass(frozen=True)
class CityTracts:
    """A saved city graph and matching full tract polygons indexed by geographic ID.

    Population counts agree between the graph and table. Analysis treats both as read-only.
    """

    graph: nx.Graph
    tracts_df: gpd.GeoDataFrame


def read_city_tracts(
    config: PipelineConfig,
    repository_root: Path,
    city_code: str,
    state_code: str,
    year: int,
) -> CityTracts:
    """Load a maximum-city graph and require its joined tract identities and counts to agree.

    Only graph-selected tracts are read from the joined state table. Their full polygons are
    projected to ESRI:102003. This compares identities and study counts; it does not reconstruct
    graph adjacency or repeat upstream population validation.

    Args:
        config (PipelineConfig): Definition vintage and input folders. Inputs always use the
            maximum-city study-area type, regardless of the configured type.
        repository_root (Path): Base for relative configured input directories.
        city_code (str): Seven-digit state/place code identifying exactly one saved definition.
        state_code (str): Two-digit state FIPS code containing the city.
        year (int): Census year of the tract graph and joined polygons.

    Returns:
        CityTracts: Saved city graph and its full tract polygons, sorted and indexed by
            geographic ID. Graph node order is not changed.

    Raises:
        OSError: A graph archive, definition table, or joined table cannot be read.
        ValueError: Archive inventory is inconsistent, the city definition is not unique, or
            tract identities/counts disagree.
        KeyError: A required area, archive member, or column is absent.
    """
    graph_directory = repository_root / config.graph_archive_directory
    base_path = graph_directory / f"max_city_{config.study_area_vintage}_{year}_tracts.zip"
    summary_df = read_graph_selection_summary(base_path, year, GeographyLevel.TRACT)
    definitions_df = pd.read_parquet(
        repository_root
        / config.study_area_directory
        / "max_city"
        / str(config.study_area_vintage)
        / "definitions.parquet",
        columns=[StudyAreaColumn.STUDY_AREA_ID, StudyAreaColumn.SELECTED_PLACE_ID],
    )
    area_ids = definitions_df.loc[
        definitions_df[StudyAreaColumn.SELECTED_PLACE_ID].eq(city_code),
        StudyAreaColumn.STUDY_AREA_ID,
    ].tolist()

    if len(area_ids) != 1:
        raise ValueError(f"Expected one saved maximum-city definition for {city_code}")

    summary = summary_df.set_index(StudyAreaColumn.STUDY_AREA_ID).loc[area_ids[0]]
    graph = read_graph_from_archive(graph_directory / summary["archive"], summary["graph_member"])
    population_path = build_population_output_path(year, GeographyLevel.TRACT, state_code)
    geography_path = build_join_output_paths(population_path)[0]
    tracts_df = (
        gpd.read_parquet(
            repository_root / config.joined_geography_directory / geography_path,
            filters=[(GeographyColumn.GEOGRAPHIC_ID, "in", list(graph))],
        )
        .to_crs("ESRI:102003")
        .set_index(GeographyColumn.GEOGRAPHIC_ID, drop=False)
        .sort_index()
    )
    graph_counts_df = pd.DataFrame.from_dict(dict(graph.nodes(data=True)), orient="index")
    graph_counts_df = graph_counts_df[[*PopulationColumn]].sort_index()

    if (
        not tracts_df.index.equals(graph_counts_df.index)
        or not tracts_df[[*PopulationColumn]].eq(graph_counts_df).to_numpy().all()
    ):
        raise ValueError(f"Joined tracts disagree with saved city graph: {city_code}, {year}")

    return CityTracts(graph=graph, tracts_df=gpd.GeoDataFrame(tracts_df, crs="ESRI:102003"))
