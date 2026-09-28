"""Read graph archive inventories and check saved graph identities and population accounting."""

import pandas as pd
from gerrychain import Graph

from national_pipeline.assign_study_areas.study_area_columns import (
    MembershipColumn,
    StudyAreaColumn,
)
from national_pipeline.pipeline_config import PipelineConfig
from national_pipeline.population_table_columns import PopulationColumn


def check_graph_population_accounting(
    graph: Graph, graph_summary: pd.Series, config: PipelineConfig
) -> None:
    """Require a loaded graph to reproduce its summary identity, sizes, and retained populations.

    Args:
        graph (Graph): Loaded graph with integer study counts and population-loss metadata.
        graph_summary (pd.Series): This area's archive-summary row.
        config (PipelineConfig): Expected study-area type and definition vintage.

    Raises:
        ValueError: Graph identity, counts, population definitions, or saved accounting disagree.
            Missing required attributes propagate as KeyError to the stage runner.
    """
    area_id = graph_summary[StudyAreaColumn.STUDY_AREA_ID]

    if (
        graph.graph[StudyAreaColumn.STUDY_AREA_ID] != area_id
        or graph.graph[MembershipColumn.CENSUS_YEAR] != graph_summary[MembershipColumn.CENSUS_YEAR]
        or graph.graph[MembershipColumn.GEOGRAPHY_LEVEL]
        != graph_summary[MembershipColumn.GEOGRAPHY_LEVEL]
        or graph.graph[StudyAreaColumn.STUDY_AREA_TYPE] != config.study_area_type
        or graph.graph[StudyAreaColumn.DEFINITION_YEAR] != config.study_area_vintage
    ):
        raise ValueError(f"Graph identity disagrees with its archive or configuration: {area_id}")

    if (
        graph.number_of_nodes() != graph_summary["node_count"]
        or graph.number_of_edges() != graph_summary["edge_count"]
    ):
        raise ValueError(f"Saved node or edge counts disagree with the graph: {area_id}")

    for _, attributes in graph.nodes(data=True):
        for column in PopulationColumn:
            count = attributes[column]

            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"Graph counts must be nonnegative integers: {area_id} {column}")

        if (
            attributes[PopulationColumn.POC]
            != attributes[PopulationColumn.TOTAL] - attributes[PopulationColumn.NON_HISPANIC_WHITE]
            or not 0
            < attributes[PopulationColumn.NON_HISPANIC_WHITE]
            + attributes[PopulationColumn.NON_HISPANIC_BLACK]
            <= attributes[PopulationColumn.TOTAL]
        ):
            raise ValueError(
                f"Graph violates the population definitions or White–Black filter: {area_id}"
            )

    for column in PopulationColumn:
        retained_count = sum(attributes[column] for _, attributes in graph.nodes(data=True))
        input_count = graph_summary[f"input_{column}"]
        removed_count = graph_summary[f"removed_{column}"]

        if (
            retained_count != graph_summary[f"retained_{column}"]
            or input_count != retained_count + removed_count
            or graph.graph["retained_population"][column] != retained_count
            or graph.graph["input_population"][column] != input_count
            or graph.graph["removed_population"][column] != removed_count
        ):
            raise ValueError(f"Graph population accounting disagrees: {area_id} {column}")
