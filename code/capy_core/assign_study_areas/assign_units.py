"""Select whole Census units by representative point and account for each study-area outcome."""

from enum import StrEnum
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyarrow import parquet

from capy_core.derived_file_paths import build_join_output_paths
from capy_core.join_geographies.select_inputs import GeographyJoinInputs
from capy_core.population_table_columns import (
    GeographyColumn,
    PopulationColumn,
    PopulationSourceColumn,
)
from capy_core.retrieve_data.census.table_columns import CensusGeographyColumn

from .study_area_columns import MembershipColumn, StudyAreaColumn


class MembershipStatus(StrEnum):
    """Whether units were selected or the area is outside supported historical coverage."""

    READY = "ready"
    NO_UNITS_SELECTED = "no_units_selected"
    HISTORICAL_COVERAGE_UNAVAILABLE = "historical_coverage_unavailable"


def read_joined_state(
    joined_geography_directory: Path,
    geography_inputs: GeographyJoinInputs,
    state_code: str,
    *,
    require_complete_definition: bool = False,
) -> gpd.GeoDataFrame:
    """Read a joined state table, checking identity, populations, geometry, and exclusion files.

    Args:
        joined_geography_directory (Path): Configured joined-geography root.
        geography_inputs (GeographyJoinInputs): Expected year/level and state population paths.
        state_code (str): Expected two-digit state code.
        require_complete_definition (bool): Reject any unmatched rows for county/place definitions.
            Defaults to False for graph-node inputs, whose documented exclusions remain upstream.

    Returns:
        gpd.GeoDataFrame: Identifiers, study populations, geometry, and a name when available.
            Source tables remain unchanged; original exclusion files are not modified.

    Raises:
        OSError: Any of the three join outputs is missing or unreadable.
        ValueError: Definition coverage, identities, geometry, or population fields are invalid.
    """
    join_output_relative_paths = build_join_output_paths(
        geography_inputs.population_paths_by_state[state_code]
    )

    for join_output_relative_path in join_output_relative_paths:
        if not (joined_geography_directory / join_output_relative_path).is_file():
            raise FileNotFoundError(joined_geography_directory / join_output_relative_path)

    if require_complete_definition:
        for join_output_relative_path in join_output_relative_paths[1:]:
            if parquet.read_metadata(
                joined_geography_directory / join_output_relative_path
            ).num_rows:
                raise ValueError(
                    f"Study-area definition has unmatched records: {join_output_relative_path}"
                )

    matched_geography_path = joined_geography_directory / join_output_relative_paths[0]
    columns_to_read = [
        GeographyColumn.GEOGRAPHIC_ID,
        GeographyColumn.STATE_CODE,
        GeographyColumn.COUNTY_CODE,
        PopulationSourceColumn.CENSUS_YEAR,
        GeographyColumn.GEOGRAPHY_LEVEL,
        *PopulationColumn,
        "geometry",
    ]
    available_columns = parquet.read_schema(matched_geography_path).names
    name_column = CensusGeographyColumn.NAME if geography_inputs.census_year >= 2000 else "COUNTY"

    if name_column in available_columns:
        columns_to_read.append(name_column)

    units_df = gpd.read_parquet(matched_geography_path, columns=columns_to_read)

    for column, expected_value in (
        (GeographyColumn.STATE_CODE, state_code),
        (PopulationSourceColumn.CENSUS_YEAR, geography_inputs.census_year),
        (GeographyColumn.GEOGRAPHY_LEVEL, geography_inputs.geography_level.value),
    ):
        if not bool(units_df[column].eq(expected_value).fillna(False).all()):
            raise ValueError(f"Joined {column} disagrees with selection: {matched_geography_path}")

    geographic_ids = units_df[GeographyColumn.GEOGRAPHIC_ID]
    expected_state_prefix = f"G{state_code}0" if geography_inputs.census_year < 2000 else state_code

    if (
        geographic_ids.duplicated().any()
        or not geographic_ids.str.startswith(expected_state_prefix, na=False).all()
    ):
        raise ValueError(
            f"Joined IDs are missing, repeated, or disagree with state: {matched_geography_path}"
        )

    for column in PopulationColumn:
        if (
            not pd.api.types.is_integer_dtype(units_df[column])
            or bool(units_df[column].isna().any())
            or bool(units_df[column].lt(0).any())
        ):
            raise ValueError(
                f"Joined {column} must contain nonnegative integer counts: {matched_geography_path}"
            )

    if not bool(
        units_df[PopulationColumn.POC]
        .eq(units_df[PopulationColumn.TOTAL] - units_df[PopulationColumn.NON_HISPANIC_WHITE])
        .all()
    ) or bool(
        (
            units_df[PopulationColumn.NON_HISPANIC_WHITE]
            + units_df[PopulationColumn.NON_HISPANIC_BLACK]
        )
        .gt(units_df[PopulationColumn.TOTAL])
        .any()
    ):
        raise ValueError(f"Joined population definitions disagree: {matched_geography_path}")

    if (
        units_df.crs is None
        or units_df.geometry.isna().any()
        or units_df.geometry.is_empty.any()
        or not units_df.geometry.is_valid.all()
    ):
        raise ValueError(f"Joined geometry is absent, empty, or invalid: {matched_geography_path}")

    if require_complete_definition and units_df.empty:
        raise ValueError(f"Study-area definition table is empty: {matched_geography_path}")

    if name_column != CensusGeographyColumn.NAME and name_column in units_df:
        units_df = units_df.rename(columns={name_column: CensusGeographyColumn.NAME})

    return units_df.to_crs("ESRI:102003")


def assign_units_by_representative_point(
    units_df: gpd.GeoDataFrame,
    study_area_definitions_df: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Assign whole units wherever their representative point is covered by an area boundary.

    Args:
        units_df (gpd.GeoDataFrame): Validated joined units, including zero-population units.
        study_area_definitions_df (gpd.GeoDataFrame): Study-area IDs and whole boundaries.

    Returns:
        pd.DataFrame: study_area_id, GEOID, and study counts. A unit can belong to multiple
            overlapping areas; geometries and populations are not clipped or divided.

    Raises:
        ValueError: Study-area definitions have no coordinate reference system.
    """
    if study_area_definitions_df.crs is None:
        raise ValueError("Study-area definitions need a coordinate reference system")

    units_df = units_df.to_crs(study_area_definitions_df.crs)
    representative_points_df = gpd.GeoDataFrame(
        units_df[[GeographyColumn.GEOGRAPHIC_ID, *PopulationColumn, "geometry"]].copy(),
        crs=units_df.crs,
    )
    representative_points_df.geometry = units_df.geometry.representative_point()
    memberships_df = gpd.sjoin(
        representative_points_df,
        gpd.GeoDataFrame(
            study_area_definitions_df[[StudyAreaColumn.STUDY_AREA_ID, "geometry"]],
            crs=study_area_definitions_df.crs,
        ),
        how="inner",
        predicate="covered_by",
    )

    return (
        pd.DataFrame(
            memberships_df[
                [StudyAreaColumn.STUDY_AREA_ID, GeographyColumn.GEOGRAPHIC_ID, *PopulationColumn]
            ]
        )
        .sort_values([StudyAreaColumn.STUDY_AREA_ID, GeographyColumn.GEOGRAPHIC_ID])
        .reset_index(drop=True)
    )


def check_node_state_coverage(
    study_area_definitions_df: gpd.GeoDataFrame,
    geography_inputs: GeographyJoinInputs,
) -> set[str]:
    """Reject missing required states, returning area IDs outside historical Puerto Rico coverage.

    Args:
        study_area_definitions_df (gpd.GeoDataFrame): Definitions with actual county-code lists.
        geography_inputs (GeographyJoinInputs): Available population states for one year and level.

    Returns:
        set[str]: Areas wholly in Puerto Rico for 1980/1990, when those inputs are unsupported.
            Other missing required states are errors, including states removed by filename filters.

    Raises:
        ValueError: A definition has no counties or a supported required state is unselected.
    """
    unavailable_area_ids = set()

    for _, study_area in study_area_definitions_df.iterrows():
        required_state_codes = {
            county_id[:2] for county_id in study_area[StudyAreaColumn.COUNTY_IDS]
        }

        if not required_state_codes:
            raise ValueError(
                f"Study area {study_area[StudyAreaColumn.STUDY_AREA_ID]} has no identified counties"
            )

        if geography_inputs.census_year < 2000 and required_state_codes == {"72"}:
            unavailable_area_ids.add(study_area[StudyAreaColumn.STUDY_AREA_ID])
            continue

        missing_state_codes = required_state_codes - set(geography_inputs.population_paths_by_state)

        if missing_state_codes:
            raise ValueError(
                f"{study_area[StudyAreaColumn.STUDY_AREA_ID]}: missing {geography_inputs.census_year} "
                f"{geography_inputs.geography_level} states {sorted(missing_state_codes)}"
            )

    return unavailable_area_ids


def summarize_memberships(
    study_area_definitions_df: gpd.GeoDataFrame,
    state_membership_summary_tables: list[pd.DataFrame],
    geography_inputs: GeographyJoinInputs,
    unavailable_area_ids: set[str],
) -> pd.DataFrame:
    """Build one outcome per area/year/level, including empty and unsupported areas.

    Args:
        study_area_definitions_df (gpd.GeoDataFrame): All current study-area IDs.
        state_membership_summary_tables (list[pd.DataFrame]): Unit counts and population sums
            per state and area.
        geography_inputs (GeographyJoinInputs): Node year and geography level.
        unavailable_area_ids (set[str]): Explicitly unsupported historical Puerto Rico definitions.

    Returns:
        pd.DataFrame: Membership status, unit count, and all four population totals per area.
            Populations repeat across overlapping areas and must not be added across areas/levels.
    """
    area_population_totals_df = pd.DataFrame(
        pd.concat(state_membership_summary_tables).groupby(StudyAreaColumn.STUDY_AREA_ID).sum()
    )
    summary_df = study_area_definitions_df[[StudyAreaColumn.STUDY_AREA_ID]].merge(
        area_population_totals_df, how="left", on=StudyAreaColumn.STUDY_AREA_ID
    )

    for column in (MembershipColumn.UNIT_COUNT, *PopulationColumn):
        summary_df[column] = summary_df[column].fillna(0).astype("Int64")

    summary_df[MembershipColumn.CENSUS_YEAR] = geography_inputs.census_year
    summary_df[MembershipColumn.GEOGRAPHY_LEVEL] = geography_inputs.geography_level.value
    summary_df[MembershipColumn.STATUS] = MembershipStatus.READY.value
    summary_df.loc[summary_df[MembershipColumn.UNIT_COUNT].eq(0), MembershipColumn.STATUS] = (
        MembershipStatus.NO_UNITS_SELECTED.value
    )
    summary_df.loc[
        summary_df[StudyAreaColumn.STUDY_AREA_ID].isin(list(unavailable_area_ids)),
        MembershipColumn.STATUS,
    ] = MembershipStatus.HISTORICAL_COVERAGE_UNAVAILABLE.value

    summary_df.loc[
        summary_df[StudyAreaColumn.STUDY_AREA_ID].isin(list(unavailable_area_ids)),
        [MembershipColumn.UNIT_COUNT, *PopulationColumn],
    ] = pd.NA

    return pd.DataFrame(summary_df)
