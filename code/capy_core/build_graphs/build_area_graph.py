"""Build one study area's graph and save its files for later ZIP assembly."""

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pandas as pd

from capy_core.assign_study_areas.study_area_columns import MembershipColumn, StudyAreaColumn
from capy_core.join_geographies.select_inputs import GeographyJoinInputs
from capy_core.population_table_columns import PopulationColumn

from .construct_graph import build_connected_graph
from .graph_archives import write_graph_json
from .read_inputs import read_area_polygons


class GraphStatus(StrEnum):
    """Whether a graph exists or why an area has no graph member."""

    READY = "ready"
    NO_UNITS_SELECTED = "no_units_selected"
    NO_UNITS_AFTER_POPULATION_FILTER = "no_units_after_population_filter"
    HISTORICAL_COVERAGE_UNAVAILABLE = "historical_coverage_unavailable"


@dataclass(frozen=True)
class AreaGraphInputs:
    """One area's metadata, validated assignment, and saved membership rows.

    The definition excludes its polygon: workers read the selected Census polygons from disk.
    Tables are read-only inputs, and only the active workers' membership subsets are submitted.
    """

    definition: pd.Series
    assignment: pd.Series
    memberships_df: pd.DataFrame


@dataclass(frozen=True)
class AreaGraphFiles:
    """Saved graph/removed-unit members and their archive-summary row.

    Member paths are relative to the selection's temporary directory, which the archive builder
    owns. Areas without selected units have no files. A fully filtered area retains its CSV.
    """

    summary: dict[str, str | int | None]
    member_paths: tuple[Path, ...]


def build_and_save_area_graph(
    area_inputs: AreaGraphInputs,
    geography_inputs: GeographyJoinInputs,
    joined_geography_directory: Path,
    temporary_directory: Path,
    *,
    warn_on_polygon_overlaps: bool = True,
) -> AreaGraphFiles:
    """Build one graph and save its JSON and removed-unit CSV under unique temporary names.

    Args:
        area_inputs (AreaGraphInputs): Area metadata, validated status, and memberships.
        geography_inputs (GeographyJoinInputs): Expected node year and level.
        joined_geography_directory (Path): Joined population-polygon root.
        temporary_directory (Path): Selection-owned folder with graphs/ and removed_units/
            subfolders already created. Each area writes only its own files.
        warn_on_polygon_overlaps (bool): Report overlaps above 100 mm²; defaults to True.
            False suppresses overlap warnings without changing adjacency or population counts.

    Returns:
        AreaGraphFiles: Saved member paths and population accounting. No graph or polygon table
            is sent back to the parent process. Input tables remain unchanged.

    Raises:
        OSError: Reading or writing fails; the selection owner cleans up temporary files.
        ValueError: Joined inputs disagree with memberships, or graph construction fails.
    """
    definition = area_inputs.definition
    assignment = area_inputs.assignment
    area_id = definition[StudyAreaColumn.STUDY_AREA_ID]
    status = GraphStatus(assignment[MembershipColumn.STATUS])
    absent_count = None if status == GraphStatus.HISTORICAL_COVERAGE_UNAVAILABLE else 0
    summary = {
        StudyAreaColumn.STUDY_AREA_ID: area_id,
        MembershipColumn.CENSUS_YEAR: geography_inputs.census_year,
        MembershipColumn.GEOGRAPHY_LEVEL: geography_inputs.geography_level.value,
        MembershipColumn.STATUS: status,
        "graph_member": None,
        "node_count": absent_count,
        "edge_count": absent_count,
        "input_unit_count": absent_count,
        "removed_unit_count": absent_count,
        "initial_component_count": absent_count,
        "artificial_edge_count": absent_count,
    }

    for population_group in ("input", "retained", "removed"):
        for population_column in PopulationColumn:
            summary[f"{population_group}_{population_column}"] = absent_count

    if status != GraphStatus.READY:
        return AreaGraphFiles(summary, ())

    units_df = read_area_polygons(
        area_inputs.memberships_df, geography_inputs, joined_geography_directory
    )
    graph, removed_units_df = build_connected_graph(
        units_df, warn_on_polygon_overlaps=warn_on_polygon_overlaps
    )
    area_metadata = json.loads(str(definition.to_json()))
    graph.graph.update(area_metadata)
    graph.graph[MembershipColumn.CENSUS_YEAR] = geography_inputs.census_year
    graph.graph[MembershipColumn.GEOGRAPHY_LEVEL] = geography_inputs.geography_level.value
    graph_member = f"graphs/{area_id}.json" if graph else None

    member_paths = []

    if graph_member is not None:
        graph_path = Path(graph_member)
        write_graph_json(graph, temporary_directory / graph_path)
        member_paths.append(graph_path)

    removed_units_path = Path(f"removed_units/{area_id}.csv")
    removed_units_df.to_csv(temporary_directory / removed_units_path, index=False)
    member_paths.append(removed_units_path)
    summary.update(
        {
            MembershipColumn.STATUS: GraphStatus.READY
            if graph
            else GraphStatus.NO_UNITS_AFTER_POPULATION_FILTER,
            "graph_member": graph_member,
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
        }
    )

    for field in (
        "input_unit_count",
        "removed_unit_count",
        "initial_component_count",
        "artificial_edge_count",
    ):
        summary[field] = graph.graph[field]

    for population_group in ("input", "retained", "removed"):
        for population_column in PopulationColumn:
            summary[f"{population_group}_{population_column}"] = graph.graph[
                f"{population_group}_population"
            ][population_column]

    return AreaGraphFiles(summary, tuple(member_paths))
