"""Select matching population tables and boundary archives from the shared run configuration."""

from dataclasses import dataclass
from pathlib import Path

from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import PipelineConfig, select_graph_node_geographies
from national_pipeline.process_population.process_tables import select_population_requests
from national_pipeline.process_population.save_tables import build_population_output_paths
from national_pipeline.retrieve_data.prepare_file_requests import select_raw_file_requests
from national_pipeline.retrieve_data.raw_file_requests import (
    NhgisBoundaryFileRequest,
    TigerBoundaryFileRequest,
)


@dataclass(frozen=True)
class GeographyJoinInputs:
    """Files to join for one Census year and geography level.

    Boundary paths start at raw_data_directory. Population paths start at
    processed_population_directory and are indexed by two-digit state FIPS code. A national
    archive uses the None boundary key; only states with selected population files are processed.
    State-specific ZIPs carry their expected state code so their contents can be checked.
    """

    census_year: int
    geography_level: GeographyLevel
    boundary_paths_by_state: dict[str | None, str]
    population_paths_by_state: dict[str, Path]


def select_geography_join_inputs(config: PipelineConfig) -> list[GeographyJoinInputs]:
    """Pair selected raw boundaries with the population outputs for the same year and level.

    Filename patterns must include both sides of each join. National state reference tables
    are used for population checks rather than geographic joins. Historical selections cover the 50
    states and DC; modern selections can choose individual statewide population tables.

    Args:
        config (PipelineConfig): Shared geography selections, filename patterns, and raw folders.

    Returns:
        list[GeographyJoinInputs]: Selected joins in year/level order, without opening any files.

    Raises:
        ValueError: A selection has population tables without boundaries, boundaries without
            population tables, or no substate population tables to join.
    """
    selected_requests = select_raw_file_requests(config)
    census_requests, nhgis_requests = select_population_requests(
        selected_requests, config.raw_data_subdirectories
    )
    population_paths_by_year_and_level = build_population_output_paths(
        census_requests, nhgis_requests
    )
    boundary_paths_by_year_and_level: dict[tuple[int, GeographyLevel], dict[str | None, str]] = {}

    for request in selected_requests:
        if not isinstance(request, (TigerBoundaryFileRequest, NhgisBoundaryFileRequest)):
            continue

        year_and_level = (request.census_year, request.geography_level)
        state_code = request.state_code if isinstance(request, TigerBoundaryFileRequest) else None
        state_paths = boundary_paths_by_year_and_level.setdefault(year_and_level, {})
        state_paths[state_code] = request.destination_relative_path

    selected_years_and_levels = set(population_paths_by_year_and_level) | set(
        boundary_paths_by_year_and_level
    )
    join_inputs = []

    for census_year, geography_level in sorted(selected_years_and_levels):
        if geography_level == GeographyLevel.STATE:
            continue

        boundary_paths_by_state = boundary_paths_by_year_and_level.get(
            (census_year, geography_level), {}
        )
        population_paths = population_paths_by_year_and_level.get(
            (census_year, geography_level), {}
        )
        population_paths_by_state = {
            state_code: relative_path
            for state_code, relative_path in population_paths.items()
            if state_code is not None
        }

        if (
            boundary_paths_by_state
            and None not in boundary_paths_by_state
            and set(boundary_paths_by_state) != set(population_paths_by_state)
        ):
            raise ValueError(
                f"Select matching population and boundary states for "
                f"{census_year} {geography_level}"
            )

        if bool(boundary_paths_by_state) != bool(population_paths_by_state):
            raise ValueError(
                f"Select both boundaries and population tables for {census_year} {geography_level}"
            )

        if boundary_paths_by_state:
            join_inputs.append(
                GeographyJoinInputs(
                    census_year=census_year,
                    geography_level=geography_level,
                    boundary_paths_by_state=boundary_paths_by_state,
                    population_paths_by_state=population_paths_by_state,
                )
            )

    if not join_inputs:
        raise ValueError("Select at least one substate population table and its boundaries")

    return join_inputs


def select_graph_node_join_inputs(
    config: PipelineConfig, selected_geography_inputs: list[GeographyJoinInputs]
) -> list[GeographyJoinInputs]:
    """Keep graph-node inputs and reject filename filters that omit a configured year/level.

    Args:
        config (PipelineConfig): Requested graph-node years and levels.
        selected_geography_inputs (list[GeographyJoinInputs]): Paired population/boundary inputs
            after filename filtering, including any study-area dependencies.

    Returns:
        list[GeographyJoinInputs]: Graph-node inputs in their original order. State coverage is
            checked against study-area definitions during assignment and graph construction.

    Raises:
        ValueError: Node selections are unsupported or filename filters omit a selected pair.
    """
    expected_years_and_levels = {
        (selection.census_year, selection.geography_level)
        for selection in select_graph_node_geographies(config)
    }
    graph_node_inputs = [
        geography_inputs
        for geography_inputs in selected_geography_inputs
        if (geography_inputs.census_year, geography_inputs.geography_level)
        in expected_years_and_levels
    ]
    missing_years_and_levels = expected_years_and_levels - {
        (geography_inputs.census_year, geography_inputs.geography_level)
        for geography_inputs in graph_node_inputs
    }

    if missing_years_and_levels:
        raise ValueError(
            f"Filename filters omit configured node selections: {sorted(missing_years_and_levels)}. "
            "Restore their inputs or change the configured node years and levels."
        )

    return graph_node_inputs
