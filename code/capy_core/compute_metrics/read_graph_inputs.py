"""Read graph archive inventories and check saved graph identities and population accounting."""

from pathlib import Path
from zipfile import ZipFile

import pandas as pd
from gerrychain import Graph

from capy_core.assign_study_areas.study_area_columns import MembershipColumn, StudyAreaColumn
from capy_core.build_graphs.run_build import GraphStatus
from capy_core.geography_types import GeographyLevel
from capy_core.pipeline_config import PipelineConfig
from capy_core.population_table_columns import PopulationColumn


def read_graph_archive_summary(
    archive_path: Path, census_year: int, geography_level: GeographyLevel
) -> pd.DataFrame:
    """Read an archive's area inventory and require its ready entries to match its graph members.

    Args:
        archive_path (Path): Selected graph ZIP, read without extracting any members.
        census_year (int): Expected year of graph-node population and boundaries.
        geography_level (GeographyLevel): Expected graph-node resolution.

    Returns:
        pd.DataFrame: One outcome per area, including areas without graphs. This checks the
            inventory; graph contents and population accounting are checked when each graph loads.

    Raises:
        OSError: The archive cannot be read.
        ValueError: Summary identities, statuses, selections, or graph-member inventory disagree.
            ZIP, CSV, and missing-member errors propagate to the stage runner.
    """
    with ZipFile(archive_path) as archive:
        member_names = archive.namelist()

        with archive.open("summary.csv") as summary_file:
            summary_df = pd.read_csv(summary_file, dtype={StudyAreaColumn.STUDY_AREA_ID: str})

    area_ids = summary_df[StudyAreaColumn.STUDY_AREA_ID]

    if summary_df.empty or bool(area_ids.isna().any()) or bool(area_ids.duplicated().any()):
        raise ValueError(f"Graph summary needs one identified outcome per area: {archive_path}")

    if not bool(summary_df[MembershipColumn.CENSUS_YEAR].eq(census_year).all()) or not bool(
        summary_df[MembershipColumn.GEOGRAPHY_LEVEL].eq(geography_level).all()
    ):
        raise ValueError(f"Graph summary disagrees with requested year or level: {archive_path}")

    if not bool(summary_df[MembershipColumn.STATUS].isin(list(GraphStatus)).all()):
        raise ValueError(f"Graph summary contains an unsupported status: {archive_path}")

    ready_mask = summary_df[MembershipColumn.STATUS].eq(GraphStatus.READY)
    expected_graph_members = "graphs/" + area_ids[ready_mask] + ".json"

    if (
        len(member_names) != len(set(member_names))
        or not summary_df.loc[ready_mask, "graph_member"].eq(expected_graph_members).all()
        or summary_df.loc[~ready_mask, "graph_member"].notna().any()
        or {name for name in member_names if name.startswith("graphs/")}
        != set(expected_graph_members)
    ):
        raise ValueError(f"Graph members disagree with archive accounting: {archive_path}")

    return summary_df


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
