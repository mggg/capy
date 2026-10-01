"""Run study-area definition and Census-unit assignment from the shared pipeline configuration."""

from pathlib import Path

import geopandas as gpd
import pandas as pd
from tqdm import tqdm

from national_pipeline.data_directories import resolve_separate_output_directory
from national_pipeline.derived_file_paths import (
    build_join_output_paths,
    build_membership_output_path,
)
from national_pipeline.geography_types import GeographyLevel, StudyAreaType
from national_pipeline.join_geographies.select_inputs import (
    GeographyJoinInputs,
    select_geography_join_inputs,
)
from national_pipeline.pipeline_config import PipelineConfig
from national_pipeline.population_table_columns import GeographyColumn, PopulationColumn
from national_pipeline.retrieve_data.census.build_published_file_requests import (
    METRO_MEMBERSHIP_FILENAME,
)
from national_pipeline.retrieve_data.census.table_columns import CensusGeographyColumn
from national_pipeline.retrieve_data.prepare_file_requests import build_geography_requests
from national_pipeline.stage_files import stage_file

from .assign_units import (
    assign_units_by_representative_point,
    check_node_state_coverage,
    read_joined_state,
    summarize_memberships,
)
from .build_definitions import (
    build_city_candidates,
    build_metro_boundaries,
    build_study_area_definitions,
    rank_and_select_city_candidates,
    read_metro_counties,
)
from .count_city_populations import count_2020_city_populations_by_county
from .study_area_columns import MembershipColumn, SelectionColumn, StudyAreaColumn


def assign_study_areas(config: PipelineConfig, repository_root: Path) -> pd.DataFrame:
    """Build definitions and save memberships for configured graph-node years and resolutions.

    Outputs for this area type/vintage are removed before validating inputs, so a failed rerun
    cannot expose old memberships as current. Files are published individually; summary.parquet
    is written last, only after every selected input succeeds.

    Args:
        config (PipelineConfig): Shared input selections and raw, population, geography, and
            study-area directories. Filename filters must retain required definition inputs.
        repository_root (Path): Base for relative configured directories.

    Returns:
        pd.DataFrame: One row per area/year/level with status, unit count, and study populations.

    Raises:
        OSError: A required input is missing/unreadable or an output cannot be written.
        ValueError: Configured paths overlap inputs, required coverage is missing, or population,
            identity, geometry, or selection checks fail. Reader-specific errors also propagate.
    """
    raw_data_directory = (repository_root / config.raw_data_directory).resolve()
    population_table_directory = (repository_root / config.processed_population_directory).resolve()
    joined_geography_directory = (repository_root / config.joined_geography_directory).resolve()
    study_area_root = resolve_separate_output_directory(
        repository_root,
        config.study_area_directory,
        (raw_data_directory, population_table_directory, joined_geography_directory),
    )

    study_area_output_directory = (
        study_area_root / config.study_area_type.value / str(config.study_area_vintage)
    )
    remove_previous_assignments(study_area_output_directory)
    selected_geography_inputs = select_geography_join_inputs(config)
    graph_node_input_groups = [
        geography_inputs
        for geography_inputs in selected_geography_inputs
        if geography_inputs.census_year in config.census_geography_years
        and geography_inputs.geography_level in config.census_geography_levels
    ]

    expected_node_years_and_levels = {
        (request.census_year, request.geography_level)
        for request in build_geography_requests(config)
        if request.census_year in config.census_geography_years
        and request.geography_level in config.census_geography_levels
    }
    selected_node_years_and_levels = {
        (geography_inputs.census_year, geography_inputs.geography_level)
        for geography_inputs in graph_node_input_groups
    }
    missing_node_years_and_levels = expected_node_years_and_levels - selected_node_years_and_levels

    if missing_node_years_and_levels:
        raise ValueError(
            "Filename filters omit configured node selections: "
            f"{sorted(missing_node_years_and_levels)}. "
            "Restore their inputs or change the configured node years and levels."
        )

    study_area_definitions_df, selection_candidates_df, city_county_populations_df = (
        prepare_study_area_definitions(
            config,
            selected_geography_inputs,
            raw_data_directory,
            population_table_directory,
            joined_geography_directory,
        )
    )

    for geography_inputs in graph_node_input_groups:
        check_node_state_coverage(study_area_definitions_df, geography_inputs)

        for population_relative_path in geography_inputs.population_paths_by_state.values():
            for join_output_relative_path in build_join_output_paths(population_relative_path):
                if not (joined_geography_directory / join_output_relative_path).is_file():
                    raise FileNotFoundError(joined_geography_directory / join_output_relative_path)

    save_assignment_table(
        study_area_definitions_df, study_area_output_directory / "definitions.parquet"
    )
    save_assignment_table(
        selection_candidates_df, study_area_output_directory / "candidates.parquet"
    )
    save_assignment_table(
        city_county_populations_df, study_area_output_directory / "city_county_populations.parquet"
    )
    membership_summary_tables = []

    for geography_inputs in graph_node_input_groups:
        membership_summary_tables.append(
            assign_selected_units(
                study_area_definitions_df,
                geography_inputs,
                joined_geography_directory,
                study_area_output_directory,
            )
        )

    summary_df = pd.concat(membership_summary_tables, ignore_index=True)
    save_assignment_table(summary_df, study_area_output_directory / "summary.parquet")

    return summary_df


def prepare_study_area_definitions(
    config: PipelineConfig,
    selected_geography_inputs: list[GeographyJoinInputs],
    raw_data_directory: Path,
    population_table_directory: Path,
    joined_geography_directory: Path,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, pd.DataFrame]:
    """Load definition inputs and execute the county or metro population-selection rule.

    Args:
        config (PipelineConfig): Definition type/vintage and configured raw subdirectories.
        selected_geography_inputs (list[GeographyJoinInputs]): Selected boundary and population
            paths, grouped by Census year and geography level.
        raw_data_directory (Path): Raw data root, including the metro workbook and block archives.
        population_table_directory (Path): Processed population root, used for 2020 block checks.
        joined_geography_directory (Path): Joined geography root, supplying counties and places.

    Returns:
        tuple[gpd.GeoDataFrame, pd.DataFrame, pd.DataFrame]: Definitions, candidate scores, and
            city/county population counts (empty when city ranking is not requested).

    Raises:
        OSError: A required input cannot be read.
        ValueError: Definition inputs are missing/incomplete or candidate population checks fail.
    """
    geography_inputs_by_year_and_level = {
        (geography_inputs.census_year, geography_inputs.geography_level): geography_inputs
        for geography_inputs in selected_geography_inputs
    }
    county_year_and_level = (config.study_area_vintage, GeographyLevel.COUNTY)

    if county_year_and_level not in geography_inputs_by_year_and_level:
        raise ValueError("Select county populations and boundaries for the study-area vintage")

    counties_df = load_definition_geography(
        joined_geography_directory, geography_inputs_by_year_and_level[county_year_and_level]
    )
    counties_df[StudyAreaColumn.COUNTY_ID] = (
        counties_df[GeographyColumn.STATE_CODE] + counties_df[GeographyColumn.COUNTY_CODE]
    )
    metros_df, places_df, city_candidates_df = None, None, None
    city_county_populations_df = pd.DataFrame(
        columns=pd.Index(
            [
                SelectionColumn.PLACE_ID,
                StudyAreaColumn.COUNTY_ID,
                SelectionColumn.BLOCK_POPULATION,
            ]
        )
    )

    if config.study_area_type != StudyAreaType.COUNTY:
        metro_membership_workbook_path = (
            raw_data_directory
            / config.raw_data_subdirectories.metro_membership_tables
            / METRO_MEMBERSHIP_FILENAME
        )
        metro_counties_df = read_metro_counties(metro_membership_workbook_path)
        metros_df = build_metro_boundaries(counties_df, metro_counties_df)

        if config.study_area_type == StudyAreaType.MAX_CITY:
            place_year_and_level, block_year_and_level = (
                (2020, GeographyLevel.PLACE),
                (2020, GeographyLevel.BLOCK),
            )

            if (
                place_year_and_level not in geography_inputs_by_year_and_level
                or block_year_and_level not in geography_inputs_by_year_and_level
            ):
                raise ValueError("City ranking requires selected 2020 place and block inputs")

            place_geography_inputs = geography_inputs_by_year_and_level[place_year_and_level]

            if set(place_geography_inputs.population_paths_by_state) != set(
                geography_inputs_by_year_and_level[county_year_and_level].population_paths_by_state
            ):
                raise ValueError("City ranking requires places for every definition-county state")

            places_df = load_definition_geography(
                joined_geography_directory, place_geography_inputs
            )
            city_candidates_df = build_city_candidates(places_df, metros_df)
            candidate_places_df = places_df.loc[
                places_df[GeographyColumn.GEOGRAPHIC_ID].isin(
                    city_candidates_df[SelectionColumn.PLACE_ID]
                )
            ]
            city_county_populations_df = count_2020_city_populations_by_county(
                candidate_places_df,
                geography_inputs_by_year_and_level[block_year_and_level],
                raw_data_directory,
                population_table_directory,
            )
            city_candidates_df = rank_and_select_city_candidates(
                city_candidates_df, city_county_populations_df, metro_counties_df
            )

    study_area_definitions_df, selection_candidates_df = build_study_area_definitions(
        counties_df,
        config.study_area_type,
        config.study_area_vintage,
        metros_df,
        places_df,
        city_candidates_df,
    )

    return study_area_definitions_df, selection_candidates_df, city_county_populations_df


def load_definition_geography(
    joined_geography_directory: Path,
    geography_inputs: GeographyJoinInputs,
) -> gpd.GeoDataFrame:
    """Load complete county or place tables, rejecting unmatched records and missing names.

    Args:
        joined_geography_directory (Path): Joined geography root.
        geography_inputs (GeographyJoinInputs): County or place paths at the definition vintage.

    Returns:
        gpd.GeoDataFrame: Complete, named units in the pipeline's projected metre CRS.

    Raises:
        OSError: An input cannot be read.
        ValueError: An input is incomplete or lacks usable names or unique geographic identities.
    """
    state_geography_tables = [
        read_joined_state(
            joined_geography_directory,
            geography_inputs,
            state_code,
            require_complete_definition=True,
        )
        for state_code in sorted(geography_inputs.population_paths_by_state)
    ]
    geography_df = gpd.GeoDataFrame(
        pd.concat(state_geography_tables, ignore_index=True), crs=state_geography_tables[0].crs
    )

    if (
        CensusGeographyColumn.NAME not in geography_df
        or geography_df[CensusGeographyColumn.NAME].fillna("").str.strip().eq("").any()
        or geography_df[GeographyColumn.GEOGRAPHIC_ID].duplicated().any()
    ):
        raise ValueError("Study-area definitions require names and unique geographic IDs")

    return geography_df


def assign_selected_units(
    study_area_definitions_df: gpd.GeoDataFrame,
    geography_inputs: GeographyJoinInputs,
    joined_geography_directory: Path,
    study_area_output_directory: Path,
) -> pd.DataFrame:
    """Save state-partitioned membership rows and summarize every area for one year and level.

    Args:
        study_area_definitions_df (gpd.GeoDataFrame): Current study-area boundaries and identifiers.
        geography_inputs (GeographyJoinInputs): Graph-node population and boundary paths by state.
        joined_geography_directory (Path): Joined inputs, never modified.
        study_area_output_directory (Path): This study-area type/vintage's output folder.

    Returns:
        pd.DataFrame: Area outcomes and population accounting for this node selection.

    Raises:
        OSError: Reading inputs or writing memberships fails.
        ValueError: Required state coverage or joined data fails validation.
    """
    unavailable_area_ids = check_node_state_coverage(study_area_definitions_df, geography_inputs)
    available_definitions_df = study_area_definitions_df.loc[
        ~study_area_definitions_df[StudyAreaColumn.STUDY_AREA_ID].isin(list(unavailable_area_ids))
    ]
    state_membership_summary_tables = []

    for state_code, population_relative_path in tqdm(
        sorted(geography_inputs.population_paths_by_state.items()),
        desc=f"{geography_inputs.census_year} {geography_inputs.geography_level} memberships",
        unit="state",
        disable=None,
    ):
        units_df = read_joined_state(joined_geography_directory, geography_inputs, state_code)
        memberships_df = assign_units_by_representative_point(units_df, available_definitions_df)
        state_totals_df = pd.DataFrame(
            memberships_df.groupby(StudyAreaColumn.STUDY_AREA_ID)[[*PopulationColumn]].sum()
        )
        state_totals_df[MembershipColumn.UNIT_COUNT] = memberships_df.groupby(
            StudyAreaColumn.STUDY_AREA_ID
        ).size()
        state_membership_summary_tables.append(state_totals_df.reset_index())
        matched_geography_relative_path, _, _ = build_join_output_paths(population_relative_path)
        memberships_df[MembershipColumn.GEOGRAPHY_FILE] = str(matched_geography_relative_path)
        membership_relative_path = build_membership_output_path(population_relative_path)
        save_assignment_table(
            memberships_df, study_area_output_directory / "memberships" / membership_relative_path
        )

    return summarize_memberships(
        study_area_definitions_df,
        state_membership_summary_tables,
        geography_inputs,
        unavailable_area_ids,
    )


def save_assignment_table(records_df: pd.DataFrame, output_path: Path) -> None:
    """Write a Parquet or GeoParquet table atomically, retaining any previous file on write failure."""
    with stage_file(output_path.parent) as temporary_path:
        records_df.to_parquet(temporary_path, compression="zstd", index=False)
        temporary_path.replace(output_path)


def remove_previous_assignments(study_area_output_directory: Path) -> None:
    """Remove this type/vintage's named outputs before a rerun, including old empty selections."""
    for filename in (
        "summary.parquet",
        "definitions.parquet",
        "candidates.parquet",
        "city_county_populations.parquet",
    ):
        (study_area_output_directory / filename).unlink(missing_ok=True)

    for membership_path in (study_area_output_directory / "memberships").rglob(
        "*_memberships.parquet"
    ):
        membership_path.unlink()
