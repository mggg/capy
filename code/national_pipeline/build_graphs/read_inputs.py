"""Read saved study-area memberships and reconcile them with their joined population polygons."""

from pathlib import Path

import geopandas as gpd
import pandas as pd
from tqdm import tqdm

from national_pipeline.assign_study_areas.assign_units import (
    MembershipStatus,
    assign_units_by_representative_point,
    check_node_state_coverage,
    read_joined_state,
)
from national_pipeline.assign_study_areas.study_area_columns import (
    MembershipColumn,
    StudyAreaColumn,
)
from national_pipeline.derived_file_paths import (
    build_join_output_paths,
    build_membership_output_path,
)
from national_pipeline.join_geographies.select_inputs import GeographyJoinInputs
from national_pipeline.pipeline_config import PipelineConfig
from national_pipeline.population_table_columns import (
    GeographyColumn,
    PopulationColumn,
    PopulationSourceColumn,
)


def read_study_area_definitions(
    study_area_directory: Path, config: PipelineConfig
) -> gpd.GeoDataFrame:
    """Load saved definitions and require unique IDs with the configured area type and vintage.

    Args:
        study_area_directory (Path): Assignment output folder for this area type and vintage.
        config (PipelineConfig): Expected study-area type and definition year.

    Returns:
        gpd.GeoDataFrame: Definitions in stable study-area ID order.

    Raises:
        OSError: Definitions cannot be read.
        ValueError: Identities, definition settings, or geometry are invalid.
    """
    definitions_df = gpd.read_parquet(study_area_directory / "definitions.parquet")
    area_ids = definitions_df[StudyAreaColumn.STUDY_AREA_ID]

    if definitions_df.empty:
        raise ValueError("Study-area definitions contain no areas")

    if area_ids.duplicated().any() or not area_ids.str.fullmatch(r"[a-z_]+[0-9]+", na=False).all():
        raise ValueError("Study-area IDs must be unique and match the expected name format")

    area_types_match = (
        definitions_df[StudyAreaColumn.STUDY_AREA_TYPE].eq(config.study_area_type).fillna(False)
    )

    if not bool(area_types_match.all()):
        raise ValueError(
            f"Study-area types must match the configured type: {config.study_area_type}"
        )

    definition_years_match = (
        definitions_df[StudyAreaColumn.DEFINITION_YEAR].eq(config.study_area_vintage).fillna(False)
    )

    if not bool(definition_years_match.all()):
        raise ValueError(
            "Study-area definition years must match the configured vintage: "
            f"{config.study_area_vintage}"
        )

    if definitions_df.crs is None:
        raise ValueError("Study-area definitions need a coordinate reference system")

    if (
        definitions_df.geometry.isna().any()
        or definitions_df.geometry.is_empty.any()
        or not definitions_df.geometry.is_valid.all()
        or not definitions_df.geom_type.isin(["Polygon", "MultiPolygon"]).all()
    ):
        raise ValueError("Study-area geometries must be nonempty, valid polygons or multipolygons")

    return gpd.GeoDataFrame(
        definitions_df.sort_values(StudyAreaColumn.STUDY_AREA_ID).reset_index(drop=True),
        crs=definitions_df.crs,
    )


def read_selection_memberships(
    study_area_directory: Path,
    definitions_df: gpd.GeoDataFrame,
    geography_inputs: GeographyJoinInputs,
    joined_geography_directory: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Recompute state memberships and require agreement with saved rows and area accounting.

    Args:
        study_area_directory (Path): Folder containing definitions, memberships, and summary.
        definitions_df (gpd.GeoDataFrame): Configured study areas.
        geography_inputs (GeographyJoinInputs): Expected node year, level, and state paths.
        joined_geography_directory (Path): Joined inputs used to repeat spatial membership checks.

    Returns:
        tuple[pd.DataFrame, pd.DataFrame]: Membership rows and the selected summary rows indexed
            by study-area ID. Unavailable historical coverage retains null counts.

    Raises:
        OSError: A membership file or completed assignment summary is absent/unreadable.
        ValueError: Coverage, identities, source paths, statuses, or saved counts disagree.
    """
    unavailable_area_ids = check_node_state_coverage(definitions_df, geography_inputs)
    selected_summary_df = read_selected_assignment_summary(
        study_area_directory, definitions_df, geography_inputs
    )
    memberships_df = read_and_verify_state_memberships(
        study_area_directory,
        definitions_df,
        geography_inputs,
        joined_geography_directory,
        unavailable_area_ids,
    )
    check_membership_summary(memberships_df, selected_summary_df, unavailable_area_ids)

    return memberships_df, selected_summary_df


def read_selected_assignment_summary(
    study_area_directory: Path,
    definitions_df: gpd.GeoDataFrame,
    geography_inputs: GeographyJoinInputs,
) -> pd.DataFrame:
    """Read one year and level's saved summary and require one outcome per configured study area.

    Args:
        study_area_directory (Path): Folder containing the completed assignment summary.
        definitions_df (gpd.GeoDataFrame): Configured study areas whose IDs must appear once each.
        geography_inputs (GeographyJoinInputs): Census year and geography level to read.

    Returns:
        pd.DataFrame: Selected summary rows indexed by study-area ID. Counts and statuses are
            checked against memberships separately by check_membership_summary().

    Raises:
        OSError: The assignment summary cannot be read.
        ValueError: Selected summary IDs are repeated or differ from the configured study areas.
    """
    assignment_summary_df = pd.read_parquet(study_area_directory / "summary.parquet")
    selected_summary_df = assignment_summary_df.loc[
        assignment_summary_df[MembershipColumn.CENSUS_YEAR].eq(geography_inputs.census_year)
        & assignment_summary_df[MembershipColumn.GEOGRAPHY_LEVEL].eq(
            geography_inputs.geography_level
        )
    ].set_index(StudyAreaColumn.STUDY_AREA_ID)
    expected_area_ids = set(definitions_df[StudyAreaColumn.STUDY_AREA_ID])

    if (
        selected_summary_df.index.has_duplicates
        or set(selected_summary_df.index) != expected_area_ids
    ):
        raise ValueError("Assignment summary does not contain exactly one outcome per study area")

    return selected_summary_df


def read_and_verify_state_memberships(
    study_area_directory: Path,
    definitions_df: gpd.GeoDataFrame,
    geography_inputs: GeographyJoinInputs,
    joined_geography_directory: Path,
    unavailable_area_ids: set[str],
) -> pd.DataFrame:
    """Read every selected state's memberships and compare them with a fresh spatial selection.

    Args:
        study_area_directory (Path): Folder containing saved state membership tables.
        definitions_df (gpd.GeoDataFrame): Configured study-area boundaries.
        geography_inputs (GeographyJoinInputs): Expected year, level, and state population paths.
        joined_geography_directory (Path): Joined polygons used to repeat the spatial selection.
        unavailable_area_ids (set[str]): Areas outside supported historical coverage, excluded
            from the spatial selection.

    Returns:
        pd.DataFrame: Combined saved memberships after their source paths, IDs, and populations
            agree with the spatial selection. Input files are not changed.

    Raises:
        OSError: A required membership or joined-geography file cannot be read.
        ValueError: Source paths disagree, joined inputs are invalid, or saved memberships differ
            from the spatial selection.
    """
    state_membership_tables = []

    available_definitions_df = definitions_df.loc[
        ~definitions_df[StudyAreaColumn.STUDY_AREA_ID].isin(list(unavailable_area_ids))
    ]

    for state_code, population_relative_path in tqdm(
        geography_inputs.population_paths_by_state.items(),
        desc=f"{geography_inputs.census_year} {geography_inputs.geography_level} membership checks",
        unit="state",
        disable=None,
    ):
        membership_path = (
            study_area_directory
            / "memberships"
            / build_membership_output_path(population_relative_path)
        )
        memberships_df = pd.read_parquet(membership_path)
        expected_geography_path = build_join_output_paths(population_relative_path)[0]

        if not bool(
            memberships_df[MembershipColumn.GEOGRAPHY_FILE]
            .eq(str(expected_geography_path))
            .fillna(False)
            .all()
        ):
            raise ValueError(
                f"Memberships reference an unexpected geography file: {membership_path}"
            )

        check_state_memberships(
            memberships_df,
            available_definitions_df,
            geography_inputs,
            state_code,
            joined_geography_directory,
        )
        state_membership_tables.append(memberships_df)

    return pd.concat(state_membership_tables, ignore_index=True)


def check_membership_summary(
    memberships_df: pd.DataFrame,
    selected_summary_df: pd.DataFrame,
    unavailable_area_ids: set[str],
) -> None:
    """Validate membership IDs and counts, then reconcile them with each area's saved outcome.

    Neither input table is modified.

    Args:
        memberships_df (pd.DataFrame): Combined memberships for one Census year and level.
        selected_summary_df (pd.DataFrame): Summary indexed by study-area ID, already checked by
            read_selected_assignment_summary() to contain exactly the configured areas.
        unavailable_area_ids (set[str]): Areas outside supported historical coverage. These must
            have no memberships and retain null summary counts rather than estimates of zero.

    Raises:
        ValueError: Membership IDs are missing, repeated, or unexpected; population counts are not
            nonnegative integers; or summary statuses and counts disagree with memberships.
    """
    expected_area_ids = set(selected_summary_df.index)
    identity_columns = [StudyAreaColumn.STUDY_AREA_ID, GeographyColumn.GEOGRAPHIC_ID]

    if (
        memberships_df[identity_columns].isna().to_numpy().any()
        or memberships_df.duplicated(identity_columns).any()
        or not bool(
            memberships_df[StudyAreaColumn.STUDY_AREA_ID].isin(list(expected_area_ids)).all()
        )
    ):
        raise ValueError("Memberships have missing, repeated, or unexpected identities")

    for column in PopulationColumn:
        if (
            not pd.api.types.is_integer_dtype(memberships_df[column])
            or bool(memberships_df[column].isna().any())
            or bool(memberships_df[column].lt(0).any())
        ):
            raise ValueError(f"Membership {column} must contain nonnegative integer counts")

    totals_df = pd.DataFrame(
        memberships_df.groupby(StudyAreaColumn.STUDY_AREA_ID)[[*PopulationColumn]].sum()
    )
    totals_df[MembershipColumn.UNIT_COUNT] = memberships_df.groupby(
        StudyAreaColumn.STUDY_AREA_ID
    ).size()
    totals_df = totals_df.reindex(selected_summary_df.index, fill_value=0)

    for area_id, summary in selected_summary_df.iterrows():
        if area_id in unavailable_area_ids:
            if (
                summary[MembershipColumn.STATUS] != MembershipStatus.HISTORICAL_COVERAGE_UNAVAILABLE
                or not summary.loc[[MembershipColumn.UNIT_COUNT, *PopulationColumn]].isna().all()
                or totals_df.loc[area_id, MembershipColumn.UNIT_COUNT] != 0
            ):
                raise ValueError(f"Unsupported historical area has population estimates: {area_id}")
            continue

        expected_status = (
            MembershipStatus.READY
            if totals_df.loc[area_id, MembershipColumn.UNIT_COUNT]
            else MembershipStatus.NO_UNITS_SELECTED
        )

        if summary[MembershipColumn.STATUS] != expected_status or any(
            pd.isna(summary[column]) or summary[column] != totals_df.loc[area_id, column]
            for column in (MembershipColumn.UNIT_COUNT, *PopulationColumn)
        ):
            raise ValueError(f"Memberships disagree with assignment accounting: {area_id}")


def check_state_memberships(
    saved_memberships_df: pd.DataFrame,
    definitions_df: gpd.GeoDataFrame,
    geography_inputs: GeographyJoinInputs,
    state_code: str,
    joined_geography_directory: Path,
) -> None:
    """Recompute one state's complete spatial selection and compare IDs and population counts.

    This includes polygons absent from the saved memberships and areas previously marked empty.
    Only one state's joined polygons are held at a time. Inputs are not changed.

    Args:
        saved_memberships_df (pd.DataFrame): Membership rows read from this state's saved file.
        definitions_df (gpd.GeoDataFrame): Areas available for this Census year.
        geography_inputs (GeographyJoinInputs): Expected year, level, and state source paths.
        state_code (str): Two-digit state FIPS code to check.
        joined_geography_directory (Path): Root of the current joined state tables.

    Raises:
        OSError: A required joined file cannot be read.
        ValueError: Joined input checks fail or current spatial memberships differ from saved
            rows.
    """
    units_df = read_joined_state(joined_geography_directory, geography_inputs, state_code)
    expected_memberships_df = assign_units_by_representative_point(units_df, definitions_df)
    identity_columns = [StudyAreaColumn.STUDY_AREA_ID, GeographyColumn.GEOGRAPHIC_ID]
    expected_counts_df = expected_memberships_df.set_index(identity_columns)[
        [*PopulationColumn]
    ].sort_index()
    saved_counts_df = saved_memberships_df.set_index(identity_columns)[
        [*PopulationColumn]
    ].sort_index()

    if (
        not saved_counts_df.index.equals(expected_counts_df.index)
        or not saved_counts_df.eq(expected_counts_df).fillna(False).to_numpy().all()
    ):
        raise ValueError(
            f"Saved memberships disagree with current spatial membership identities and populations: "
            f"{geography_inputs.census_year} {geography_inputs.geography_level} state {state_code}"
        )


def read_area_polygons(
    area_memberships_df: pd.DataFrame,
    geography_inputs: GeographyJoinInputs,
    joined_geography_directory: Path,
) -> gpd.GeoDataFrame:
    """Read one area's whole polygons and require their counts to equal the saved memberships.

    Parquet filters limit the returned rows to the area's IDs. Files may still be scanned, but
    only one area's polygons are held at a time rather than the national block collection.

    Args:
        area_memberships_df (pd.DataFrame): Nonempty memberships for one study area.
        geography_inputs (GeographyJoinInputs): Expected Census year and geography level.
        joined_geography_directory (Path): Root of the referenced joined GeoParquet files.

    Returns:
        gpd.GeoDataFrame: Matching populations and full polygons in the pipeline's metre CRS.

    Raises:
        OSError: A referenced file cannot be read.
        ValueError: Units are missing/repeated or populations and selection metadata disagree.
    """
    area_polygon_tables = []
    columns = [
        GeographyColumn.GEOGRAPHIC_ID,
        *PopulationColumn,
        PopulationSourceColumn.CENSUS_YEAR,
        GeographyColumn.GEOGRAPHY_LEVEL,
        "geometry",
    ]

    for geography_relative_path, memberships_df in area_memberships_df.groupby(
        MembershipColumn.GEOGRAPHY_FILE
    ):
        units_df = gpd.read_parquet(
            joined_geography_directory / str(geography_relative_path),
            columns=columns,
            filters=[
                (
                    GeographyColumn.GEOGRAPHIC_ID,
                    "in",
                    memberships_df[GeographyColumn.GEOGRAPHIC_ID].tolist(),
                )
            ],
        )

        if not bool(
            units_df[PopulationSourceColumn.CENSUS_YEAR]
            .eq(geography_inputs.census_year)
            .fillna(False)
            .all()
        ) or not bool(
            units_df[GeographyColumn.GEOGRAPHY_LEVEL]
            .eq(geography_inputs.geography_level)
            .fillna(False)
            .all()
        ):
            raise ValueError(
                f"Joined geography metadata disagrees with the selection: {geography_relative_path}"
            )

        area_polygon_tables.append(units_df.to_crs("ESRI:102003"))

    units_df = gpd.GeoDataFrame(
        pd.concat(area_polygon_tables, ignore_index=True), crs="ESRI:102003"
    )
    saved_counts_df = area_memberships_df.set_index(GeographyColumn.GEOGRAPHIC_ID)[
        [*PopulationColumn]
    ].sort_index()
    joined_counts_df = units_df.set_index(GeographyColumn.GEOGRAPHIC_ID)[
        [*PopulationColumn]
    ].sort_index()

    if (
        joined_counts_df.index.has_duplicates
        or not joined_counts_df.index.equals(saved_counts_df.index)
        or not joined_counts_df.eq(saved_counts_df).fillna(False).to_numpy().all()
    ):
        raise ValueError(
            "Joined polygons do not reproduce the membership identities and populations"
        )

    return units_df
