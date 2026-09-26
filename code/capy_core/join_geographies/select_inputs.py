"""Select matching population tables and boundary archives from the shared run configuration."""

from dataclasses import dataclass
from pathlib import Path

from capy_core.geography_types import GeographyLevel
from capy_core.pipeline_config import PipelineConfig
from capy_core.process_population.process_tables import select_population_requests
from capy_core.process_population.read_nhgis import describe_nhgis_population_request
from capy_core.process_population.save_tables import build_population_output_path
from capy_core.retrieve_data.census.build_published_file_requests import build_tiger_file_requests
from capy_core.retrieve_data.nhgis.build_requests import build_nhgis_file_requests
from capy_core.retrieve_data.prepare_file_requests import (
    build_geography_requests,
    build_raw_file_requests,
    select_raw_file_requests,
)
from capy_core.retrieve_data.raw_file_requests import NhgisBoundaryFileRequest
from capy_core.retrieve_data.state_codes import STATE_FIPS_CODES


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
    selected_raw_file_paths = {
        request.destination_relative_path
        for request in select_raw_file_requests(
            build_raw_file_requests(config), config.file_path_patterns
        )
    }
    census_requests, nhgis_requests = select_population_requests(config)
    population_paths_by_selection: dict[tuple[int, GeographyLevel], dict[str, Path]] = {}

    for request in census_requests:
        if request.state_code is None:
            continue

        year_and_level = (request.census_year, request.geography_level)
        population_paths_by_selection.setdefault(year_and_level, {})[request.state_code] = (
            build_population_output_path(
                request.census_year, request.geography_level, request.state_code
            )
        )

    for request in nhgis_requests:
        census_year, geography_level = describe_nhgis_population_request(request)

        if geography_level == GeographyLevel.STATE:
            continue

        population_paths_by_selection[census_year, geography_level] = {
            state_code: build_population_output_path(census_year, geography_level, state_code)
            for state_code in STATE_FIPS_CODES
            if state_code != "72"  # Puerto Rico is not in NHGIS substate tables
        }

    join_inputs = []

    for selection in build_geography_requests(config):
        match selection.census_year:
            case 1980 | 1990:
                boundary_requests = [
                    request
                    for request in build_nhgis_file_requests(
                        config.raw_data_subdirectories, (selection,)
                    )
                    if isinstance(request, NhgisBoundaryFileRequest)
                ]
            case 2000 | 2010 | 2020:
                boundary_requests = build_tiger_file_requests(
                    config.raw_data_subdirectories, (selection,)
                )

            case _:
                raise ValueError(f"Unsupported Census year {selection.census_year}")

        boundary_state_codes = (
            (None,)
            if selection.census_year < 2000 or selection.geography_level == GeographyLevel.COUNTY
            else STATE_FIPS_CODES
        )
        boundary_paths_by_state = {
            state_code: request.destination_relative_path
            for state_code, request in zip(boundary_state_codes, boundary_requests, strict=True)
            if request.destination_relative_path in selected_raw_file_paths
        }
        population_paths_by_state = population_paths_by_selection.get(
            (selection.census_year, selection.geography_level), {}
        )

        if (
            boundary_paths_by_state
            and None not in boundary_paths_by_state
            and set(boundary_paths_by_state) != set(population_paths_by_state)
        ):
            raise ValueError(
                f"Select matching population and boundary states for "
                f"{selection.census_year} {selection.geography_level}"
            )

        if bool(boundary_paths_by_state) != bool(population_paths_by_state):
            raise ValueError(
                f"Select both boundaries and population tables for "
                f"{selection.census_year} {selection.geography_level}"
            )

        if boundary_paths_by_state:
            join_inputs.append(
                GeographyJoinInputs(
                    census_year=selection.census_year,
                    geography_level=selection.geography_level,
                    boundary_paths_by_state=boundary_paths_by_state,
                    population_paths_by_state=population_paths_by_state,
                )
            )

    if not join_inputs:
        raise ValueError("Select at least one substate population table and its boundaries")

    return join_inputs
