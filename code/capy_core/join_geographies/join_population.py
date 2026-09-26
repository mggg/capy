"""Repair polygon geometry, attach population counts, and retain both sides of an unmatched join."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import geopandas as gpd
import pandas as pd
import shapely

from capy_core.geography_types import GeographyLevel
from capy_core.population_table_columns import (
    GeographyColumn,
    PopulationColumn,
    PopulationSourceColumn,
)
from capy_core.retrieve_data.nhgis.table_columns import NhgisGeographyColumn

from .read_1990_zero_blocks import (
    CONFLICTING_1990_ZERO_BLOCK_ID,
    CONFLICTING_1990_ZERO_BLOCK_POPULATION,
    read_1990_zero_population_block_ids,
)
from .read_boundaries import BoundaryColumn
from .repair_1980_sources import PARENT_GEOMETRY_MERGES_1980

if TYPE_CHECKING:
    from .select_inputs import GeographyJoinInputs

PROJECTED_CRS = "ESRI:102003"


class JoinColumn(StrEnum):
    """Geometry accounting and source limitations saved alongside geographic records."""

    BOUNDARY_PART_COUNT = "BOUNDARY_PART_COUNT"
    MERGED_BOUNDARY_SOURCES = "MERGED_BOUNDARY_SOURCES"
    EXCLUSION_REASON = "EXCLUSION_REASON"
    KNOWN_TOTAL_POPULATION = "KNOWN_TOTAL_POPULATION"
    GEOGRAPHY_NOTE = "GEOGRAPHY_NOTE"


class ExclusionReason(StrEnum):
    """Why a record remains outside the population-attributed geography table.

    A source-supported exclusion explains an absent match; it does not supply a missing polygon or
    invent a population assignment. UNRESOLVED remains a valid, explicitly reported outcome.
    """

    UNRESOLVED = "unresolved_correspondence"
    UNTRACTED_REMAINDER_1980 = "1980_untracted_county_remainder"
    SHIP_CREW = "ship_crew_record_without_land_boundary"
    ZERO_POPULATION_WITHOUT_BOUNDARY = "zero_population_record_without_boundary"
    WATER_BLOCK_1990 = "1990_water_block_absent_from_population_tables"
    EMPTY_BLOCK_1990 = "1990_block_confirmed_empty_by_original_census_tables"
    UNASSIGNED_PLACEHOLDER = "placeholder_without_proven_population_parent"


@dataclass(frozen=True)
class PopulationBoundaryJoin:
    """Matched boundaries and the complete records left unmatched on either side.

    Population columns appear only where population records exist. Unmatched polygons instead
    carry KNOWN_TOTAL_POPULATION, which is null unless 1990 water-block numbering or original
    Census population records establish zero.
    """

    matched_geography_df: gpd.GeoDataFrame
    unmatched_population_df: pd.DataFrame
    unmatched_boundaries_df: gpd.GeoDataFrame


def repair_and_project_boundaries(
    boundaries_df: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Repair invalid polygons with buffer(0), check the result, and project to study coordinates.

    Repair occurs in the source coordinate system and preserves IDs and existing merge accounting. The
    returned accounting measures each repaired feature's area before and after in square meters,
    using ESRI:102003. It describes geometry changes, not residents gained or lost. Empty or
    non-polygon results stop processing instead of disappearing from the join.

    Args:
        boundaries_df (gpd.GeoDataFrame): Source polygons with a known CRS and unique GEOIDs.

    Returns:
        tuple[gpd.GeoDataFrame, pd.DataFrame]: Valid projected boundaries and one accounting row
            per repaired feature, including the original reason for invalidity and areas.

    Raises:
        ValueError: The CRS, identifiers, input geometries, or repaired polygons are unusable.
    """
    check_unique_identifiers(boundaries_df, "Boundary")

    if boundaries_df.crs is None:
        raise ValueError("Boundary coordinates must declare their CRS")

    if (boundaries_df.geometry.isna() | boundaries_df.geometry.is_empty).any():
        raise ValueError("Missing or empty boundary geometry")

    if not boundaries_df.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("Boundary geometries must be polygons")

    boundaries_df = boundaries_df.copy()
    invalid_geometry_rows = ~boundaries_df.is_valid
    repaired_geometries = boundaries_df.loc[invalid_geometry_rows].geometry.buffer(0)

    repairs_df = boundaries_df.loc[invalid_geometry_rows].drop(columns="geometry").copy()
    repairs_df["invalidity_reason"] = shapely.is_valid_reason(
        boundaries_df.loc[invalid_geometry_rows].geometry
    )
    repairs_df["area_before_m2"] = (
        boundaries_df.loc[invalid_geometry_rows].to_crs(PROJECTED_CRS).area
    )
    repairs_df["area_after_m2"] = repaired_geometries.to_crs(PROJECTED_CRS).area

    boundaries_df.loc[invalid_geometry_rows, "geometry"] = repaired_geometries

    boundaries_df = boundaries_df.to_crs(PROJECTED_CRS)

    if (
        not boundaries_df.is_valid.all()
        or boundaries_df.is_empty.any()
        or not boundaries_df.geom_type.isin(["Polygon", "MultiPolygon"]).all()
    ):
        raise ValueError("buffer(0) and projection did not produce valid nonempty polygons")

    return boundaries_df, repairs_df


def merge_1980_parent_geometries(boundaries_df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Merge four documented 1980 fragments into their population parents, without adding people.

    The complete national tract/BNA archive must be present. Each source and parent is checked
    once, and their union must be valid. The retained parent lists the fragment's original source
    location; BOUNDARY_PART_COUNT accounts for both source features.

    Args:
        boundaries_df (gpd.GeoDataFrame): Complete projected 1980 tract/BNA table with source
            file/member columns. Preparation must initialize BOUNDARY_PART_COUNT to 1 and
            MERGED_BOUNDARY_SOURCES to an empty string for each original feature.

    Returns:
        gpd.GeoDataFrame: Four fewer rows, with parent geometries extended and IDs unchanged.

    Raises:
        ValueError: A fragment or parent is missing, or merging produces an invalid polygon.
        KeyError: Required identity, provenance, or boundary accounting columns are absent.
    """
    boundaries_df = boundaries_df.copy()
    boundaries_df.set_index(GeographyColumn.GEOGRAPHIC_ID, drop=False, inplace=True)

    for fragment_id, parent_id in PARENT_GEOMETRY_MERGES_1980.items():
        if fragment_id not in boundaries_df.index or parent_id not in boundaries_df.index:
            raise ValueError(f"1980 geometry repair requires {fragment_id} and {parent_id}")

        fragment_record = boundaries_df.loc[fragment_id]
        parent_geometry = boundaries_df.at[parent_id, "geometry"]
        merged_geometry = parent_geometry.union(fragment_record.geometry)

        if not merged_geometry.is_valid or merged_geometry.is_empty:
            raise ValueError(f"Invalid merged 1980 geometry for {parent_id}")

        boundaries_df.at[parent_id, "geometry"] = merged_geometry
        boundaries_df.at[parent_id, JoinColumn.BOUNDARY_PART_COUNT] += 1
        boundaries_df.at[parent_id, JoinColumn.MERGED_BOUNDARY_SOURCES] = (
            f"{fragment_record[BoundaryColumn.SOURCE_FILE]}!"
            f"{fragment_record[BoundaryColumn.SOURCE_MEMBER]}:{fragment_id}"
        )
        boundaries_df.drop(index=fragment_id, inplace=True)

    boundaries_df.reset_index(drop=True, inplace=True)

    return boundaries_df


def check_unique_identifiers(records_df: pd.DataFrame, table_description: str) -> None:
    """Reject missing, non-string, blank, or repeated GEOIDs before matching records.

    Args:
        records_df (pd.DataFrame): Population or boundary records containing GEOID.
        table_description (str): Label used to identify the table in an error message.

    Raises:
        KeyError: The GEOID column is absent.
        ValueError: An identifier is missing, blank, not a string, or repeated.
    """
    geographic_ids = records_df[GeographyColumn.GEOGRAPHIC_ID]

    if (
        bool(geographic_ids.isna().any())
        or not bool(
            geographic_ids.map(lambda value: isinstance(value, str) and bool(value.strip())).all()
        )
        or bool(geographic_ids.duplicated().any())
    ):
        raise ValueError(f"{table_description} GEOIDs must be nonempty unique strings")


def check_population_join_input(
    population_df: pd.DataFrame, census_year: int, geography_level: GeographyLevel, state_code: str
) -> None:
    """Check that a processed table belongs to its requested file and still has valid counts.

    Args:
        population_df (pd.DataFrame): Processed population Parquet contents.
        census_year (int): Year expected from the configuration.
        geography_level (GeographyLevel): Expected resolution.
        state_code (str): Expected two-digit state code.

    Raises:
        ValueError: Required columns, identity metadata, or population arithmetic are invalid.
    """
    required_columns = {
        *PopulationColumn,
        *[
            column
            for column in PopulationSourceColumn
            if column != PopulationSourceColumn.SOURCE_MEMBER
        ],
        GeographyColumn.GEOGRAPHIC_ID,
        GeographyColumn.STATE_CODE,
        GeographyColumn.GEOGRAPHY_LEVEL,
    }

    if not required_columns.issubset(population_df.columns) or population_df.empty:
        raise ValueError("Processed population table is empty or lacks required columns")

    check_unique_identifiers(population_df, "Population")

    for column, expected_value in (
        (PopulationSourceColumn.CENSUS_YEAR, census_year),
        (GeographyColumn.GEOGRAPHY_LEVEL, geography_level.value),
        (GeographyColumn.STATE_CODE, state_code),
    ):
        if not bool(population_df[column].eq(expected_value).all()):
            raise ValueError(f"Population {column} disagrees with the requested {expected_value}")

    state_id_prefix = f"G{state_code}0" if census_year < 2000 else state_code

    if not bool(population_df[GeographyColumn.GEOGRAPHIC_ID].str.startswith(state_id_prefix).all()):
        raise ValueError("Population GEOID disagrees with its state")

    if census_year < 2000:
        historical_columns = {
            NhgisGeographyColumn.GEOGRAPHIC_ID,
            NhgisGeographyColumn.STATE_CODE,
            NhgisGeographyColumn.COUNTY_CODE,
        }

        if not historical_columns.issubset(population_df.columns):
            raise ValueError("Historical population table lacks source geographic components")

        expected_components = {
            NhgisGeographyColumn.GEOGRAPHIC_ID: population_df[GeographyColumn.GEOGRAPHIC_ID],
            NhgisGeographyColumn.STATE_CODE: population_df[GeographyColumn.STATE_CODE],
            NhgisGeographyColumn.COUNTY_CODE: population_df[GeographyColumn.GEOGRAPHIC_ID].str[4:7],
        }

        for column, expected_values in expected_components.items():
            if not bool(population_df[column].eq(expected_values).all()):
                raise ValueError(f"Historical population {column} disagrees with its geographic ID")

    for column in PopulationColumn:
        if (
            not pd.api.types.is_integer_dtype(population_df[column])
            or bool(population_df[column].isna().any())
            or bool(population_df[column].lt(0).any())
        ):
            raise ValueError(f"{column} must contain nonnegative integer counts")

    expected_poc_counts = (
        population_df[PopulationColumn.TOTAL] - population_df[PopulationColumn.WHITE]
    )
    white_black_counts = (
        population_df[PopulationColumn.WHITE] + population_df[PopulationColumn.BLACK]
    )

    if not bool(population_df[PopulationColumn.POC].eq(expected_poc_counts).all()) or bool(
        white_black_counts.gt(population_df[PopulationColumn.TOTAL]).any()
    ):
        raise ValueError("Processed population definitions are inconsistent")


def join_population_to_boundaries(
    boundaries_df: gpd.GeoDataFrame,
    population_df: pd.DataFrame,
    census_year: int,
    geography_level: GeographyLevel,
) -> PopulationBoundaryJoin:
    """Match unique IDs once and preserve every unmatched record with an explanation.

    State and county identities must agree where a population row matches a boundary. Counts
    across matched and unmatched population records must reproduce every input study total.
    Matched zero-population units remain; graph filtering belongs to a later stage.

    Args:
        boundaries_df (gpd.GeoDataFrame): Checked, repaired boundaries for one state.
        population_df (pd.DataFrame): Checked, corrected population records for the same state.
        census_year (int): Year controlling documented historical exclusions.
        geography_level (GeographyLevel): Resolution of both tables.

    Returns:
        PopulationBoundaryJoin: Matched polygons, population without polygons, and polygons
            without population. Unknown population remains null, never inferred to be zero.

    Raises:
        ValueError: IDs repeat, geographic metadata conflict, or population is not conserved.
    """
    check_unique_identifiers(boundaries_df, "Boundary")
    check_unique_identifiers(population_df, "Population")

    geographic_id_column = GeographyColumn.GEOGRAPHIC_ID
    matching_boundary_rows = boundaries_df[geographic_id_column].isin(
        population_df[geographic_id_column]
    )
    matched_boundaries_df = boundaries_df.loc[matching_boundary_rows].copy()
    population_by_id_df = population_df.set_index(geographic_id_column)

    for column in (GeographyColumn.STATE_CODE, GeographyColumn.COUNTY_CODE):
        if column not in population_df:
            continue

        expected_geographic_codes = matched_boundaries_df[geographic_id_column].map(
            population_by_id_df[column]
        )

        if not matched_boundaries_df[column].eq(expected_geographic_codes).all():
            raise ValueError(f"Boundary and population {column} disagree")

    matched_geography_df = matched_boundaries_df.merge(
        population_df.drop(
            columns=[GeographyColumn.STATE_CODE, GeographyColumn.COUNTY_CODE], errors="ignore"
        ),
        on=geographic_id_column,
        how="inner",
        validate="one_to_one",
    )

    if (
        matched_geography_df.loc[
            matched_geography_df[BoundaryColumn.WATER_BLOCK], PopulationColumn.TOTAL
        ]
        .gt(0)
        .any()
    ):
        raise ValueError("A documented 1990 water block unexpectedly has population")

    unmatched_population_df = population_df.loc[
        ~population_df[geographic_id_column].isin(boundaries_df[geographic_id_column])
    ].copy()
    unmatched_boundaries_df = boundaries_df.loc[~matching_boundary_rows].copy()

    add_exclusion_reasons_in_place(
        unmatched_population_df, unmatched_boundaries_df, census_year, geography_level
    )

    matched_geography_df[JoinColumn.GEOGRAPHY_NOTE] = ""

    if census_year == 1980 and geography_level == GeographyLevel.TRACT:
        matched_geography_df.loc[
            matched_geography_df[geographic_id_column].str.startswith("G3600110"),
            JoinColumn.GEOGRAPHY_NOTE,
        ] = (
            "Auburn-area source labels have unresolved centroid/boundary conflicts; "
            "no inferred reassignment"
        )

    for column in PopulationColumn:
        if int(population_df[column].sum()) != (
            int(matched_geography_df[column].sum()) + int(unmatched_population_df[column].sum())
        ):
            raise ValueError(f"Join did not conserve {column}")

    return PopulationBoundaryJoin(
        matched_geography_df=matched_geography_df,
        unmatched_population_df=unmatched_population_df,
        unmatched_boundaries_df=unmatched_boundaries_df,
    )


def add_exclusion_reasons_in_place(
    population_df: pd.DataFrame,
    boundaries_df: gpd.GeoDataFrame,
    census_year: int,
    geography_level: GeographyLevel,
) -> None:
    """Add documented exclusion reasons to unmatched tables in place.

    Tract suffixes identify ship-crew records, including finer 1990 records within those tracts.
    The 1990 water-block convention supplies the boundary-side classification here. A
    zero-population source record still has an unresolved boundary identity. Other unmatched
    boundaries retain unknown population, including the unassigned Denver placeholder.

    Args:
        population_df (pd.DataFrame): Population records without a matching polygon.
        boundaries_df (gpd.GeoDataFrame): Polygons without a matching population record.
        census_year (int): Year of both tables.
        geography_level (GeographyLevel): Resolution of both tables.
    """
    population_df[JoinColumn.EXCLUSION_REASON] = ExclusionReason.UNRESOLVED.value
    population_df.loc[population_df[PopulationColumn.TOTAL].eq(0), JoinColumn.EXCLUSION_REASON] = (
        ExclusionReason.ZERO_POPULATION_WITHOUT_BOUNDARY.value
    )

    if census_year in (1980, 1990) and geography_level == GeographyLevel.TRACT:
        tract_codes = population_df[GeographyColumn.GEOGRAPHIC_ID].str[8:]
        population_df.loc[tract_codes.str.fullmatch(r"[0-9]{4}99"), JoinColumn.EXCLUSION_REASON] = (
            ExclusionReason.SHIP_CREW.value
        )

        if census_year == 1980:
            population_df.loc[tract_codes.eq("999999"), JoinColumn.EXCLUSION_REASON] = (
                ExclusionReason.UNTRACTED_REMAINDER_1980.value
            )
    elif census_year == 1990 and geography_level in (
        GeographyLevel.BLOCK_GROUP,
        GeographyLevel.BLOCK,
    ):
        ship_crew_rows = population_df["TRACTA"].str.fullmatch(r"[0-9]{4}99")
        population_df.loc[ship_crew_rows, JoinColumn.EXCLUSION_REASON] = (
            ExclusionReason.SHIP_CREW.value
        )

    boundaries_df[JoinColumn.EXCLUSION_REASON] = ExclusionReason.UNRESOLVED.value
    boundaries_df[JoinColumn.KNOWN_TOTAL_POPULATION] = pd.Series(
        pd.NA, index=boundaries_df.index, dtype="Int64"
    )

    water_block_rows = boundaries_df[BoundaryColumn.WATER_BLOCK]
    boundaries_df.loc[water_block_rows, JoinColumn.EXCLUSION_REASON] = (
        ExclusionReason.WATER_BLOCK_1990.value
    )
    boundaries_df.loc[water_block_rows, JoinColumn.KNOWN_TOTAL_POPULATION] = 0

    placeholder_rows = boundaries_df[GeographyColumn.GEOGRAPHIC_ID].str.contains(
        "nodata", case=False
    )
    boundaries_df.loc[placeholder_rows, JoinColumn.EXCLUSION_REASON] = (
        ExclusionReason.UNASSIGNED_PLACEHOLDER.value
    )


def classify_1990_zero_population_blocks(
    result: PopulationBoundaryJoin,
    selection: "GeographyJoinInputs",
    state_code: str,
    block_reference_directory: Path,
) -> PopulationBoundaryJoin:
    """Read original empty-block evidence and classify the selected state's 1990 block join.

    Other years and levels return without reading reference files or changing the result.

    Args:
        result (PopulationBoundaryJoin): Join for the supplied selection and state, left unchanged.
        selection (GeographyJoinInputs): Year and level of the join.
        state_code (str): Two-digit state FIPS code whose original references should be read.
        block_reference_directory (Path): Folder containing original STF1B and PL reference files.

    Returns:
        PopulationBoundaryJoin: Annotated join, or the original result for other selections.
            Changed tables are copied; the unchanged unmatched-population table is shared.

    Raises:
        OSError: Reading a required reference fails.
        BadZipFile: A reference ZIP is damaged.
        ValueError: Reference identities or population counts disagree.
    """
    if selection.census_year != 1990 or selection.geography_level != GeographyLevel.BLOCK:
        return result

    zero_population_block_ids = read_1990_zero_population_block_ids(
        block_reference_directory, state_code
    )

    return apply_1990_zero_block_evidence(result, zero_population_block_ids)


def apply_1990_zero_block_evidence(
    result: PopulationBoundaryJoin, zero_population_block_ids: set[str]
) -> PopulationBoundaryJoin:
    """Return an annotated join using exact empty-block IDs from original Census records.

    Block 36081077398104 in Queens, NY has conflicting Census records. The original STF1B
    population table reports 106 people and 52 housing units, agreeing with NHGIS. The
    geographic-zero file repeats that ID with zero counts but a different centroid and land area.
    The reference reader excludes this ID from its empty-block evidence. If matched, the block
    must retain its 106 residents; GEOGRAPHY_NOTE records the conflict.

    Args:
        result (PopulationBoundaryJoin): Matched and unmatched 1990 blocks with normalized Census
            block IDs, left unchanged.
        zero_population_block_ids (set[str]): IDs proven to have zero people and housing units by
            the original STF1B or PL records. Missing IDs establish nothing.

    Returns:
        PopulationBoundaryJoin: Copies of the matched and unmatched-boundary tables with updated
            notes and classifications. The unchanged unmatched-population table is shared.
            No input table is changed, including when validation fails.

    Raises:
        ValueError: A matched NHGIS population contradicts the original zero-population record.
    """
    matched_geography_df = result.matched_geography_df.copy()
    known_empty_rows = matched_geography_df[BoundaryColumn.CENSUS_ID].isin(
        list(zero_population_block_ids)
    )

    if matched_geography_df.loc[known_empty_rows, PopulationColumn.TOTAL].gt(0).any():
        raise ValueError("NHGIS population contradicts an original zero-population block record")

    conflicting_reference_rows = matched_geography_df[BoundaryColumn.CENSUS_ID].eq(
        CONFLICTING_1990_ZERO_BLOCK_ID
    )

    if (
        not matched_geography_df.loc[conflicting_reference_rows, PopulationColumn.TOTAL]
        .eq(CONFLICTING_1990_ZERO_BLOCK_POPULATION)
        .all()
    ):
        raise ValueError(
            "Queens, NY block with conflicting zero reference must retain its 106 residents"
        )

    matched_geography_df.loc[conflicting_reference_rows, JoinColumn.GEOGRAPHY_NOTE] = (
        "NHGIS and original STF1B population records agree on 106 residents; "
        "a conflicting geographic-zero record is not used"
    )

    boundaries_df = result.unmatched_boundaries_df.copy()
    known_empty_rows = boundaries_df[BoundaryColumn.CENSUS_ID].isin(list(zero_population_block_ids))
    boundaries_df.loc[known_empty_rows, JoinColumn.EXCLUSION_REASON] = (
        ExclusionReason.EMPTY_BLOCK_1990.value
    )
    boundaries_df.loc[known_empty_rows, JoinColumn.KNOWN_TOTAL_POPULATION] = 0

    return PopulationBoundaryJoin(
        matched_geography_df=matched_geography_df,
        unmatched_population_df=result.unmatched_population_df,
        unmatched_boundaries_df=boundaries_df,
    )
