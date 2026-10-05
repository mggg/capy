"""Read selected Census and NHGIS boundaries without changing their geometry."""

import shutil
from collections.abc import Generator
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd
import pyogrio

from national_pipeline.geography_types import GeographyLevel
from national_pipeline.population_table_columns import GeographyColumn

# Keys identify the Census year and geography; values give the component-column suffix and ID
# column. The 2000/2010 entries describe TIGER2010 files; the 2020 entries describe TIGER2020
# files.
TIGER_IDENTIFIER_COLUMNS: dict[tuple[int, GeographyLevel], tuple[str, str]] = {
    (2000, GeographyLevel.COUNTY): ("00", "CNTYIDFP00"),
    (2000, GeographyLevel.TRACT): ("00", "CTIDFP00"),
    (2000, GeographyLevel.BLOCK_GROUP): ("00", "BKGPIDFP00"),
    (2000, GeographyLevel.BLOCK): ("00", "BLKIDFP00"),
    (2010, GeographyLevel.COUNTY): ("10", "GEOID10"),
    (2010, GeographyLevel.TRACT): ("10", "GEOID10"),
    (2010, GeographyLevel.BLOCK_GROUP): ("10", "GEOID10"),
    (2010, GeographyLevel.BLOCK): ("10", "GEOID10"),
    (2020, GeographyLevel.COUNTY): ("", "GEOID"),
    (2020, GeographyLevel.TRACT): ("", "GEOID"),
    (2020, GeographyLevel.BLOCK_GROUP): ("", "GEOID"),
    (2020, GeographyLevel.BLOCK): ("20", "GEOID20"),
    (2020, GeographyLevel.PLACE): ("", "GEOID"),
}


NHGIS_NATIONAL_LAYER_NAMES: dict[tuple[int, GeographyLevel], tuple[str, ...]] = {
    (1980, GeographyLevel.COUNTY): ("US_county_1980_conflated",),
    (1980, GeographyLevel.TRACT): ("US_bna_1980", "US_tract_1980"),
    (1990, GeographyLevel.COUNTY): ("US_county_1990_conflated",),
    (1990, GeographyLevel.TRACT): ("US_tract_1990",),
    (1990, GeographyLevel.BLOCK_GROUP): ("US_blck_grp_1990",),
}


class BoundaryColumn(StrEnum):
    """Source locations, original identifiers, and documented corrections for each boundary.

    CENSUS_ID retains the normalized Census block ID for 1990 blocks so original Census tables can
    be joined independently of NHGIS identifiers. It is empty for other years and levels.
    """

    SOURCE_FILE = "BOUNDARY_SOURCE_FILE"
    SOURCE_MEMBER = "BOUNDARY_SOURCE_MEMBER"
    SOURCE_ID = "BOUNDARY_SOURCE_ID"
    CENSUS_ID = "BOUNDARY_CENSUS_ID"
    CORRECTION = "BOUNDARY_CORRECTION"
    WATER_BLOCK = "BOUNDARY_WATER_BLOCK"


def read_boundary_archive(
    archive_path: Path,
    source_archive_relative_path: str,
    census_year: int,
    geography_level: GeographyLevel,
) -> Generator[gpd.GeoDataFrame, None, None]:
    """Read boundary tables with consistent identifiers and pointers to the original records.

    The 2000–2020 TIGER files yield one table. The 1980/1990 NHGIS files contain inner ZIPs:
    national files yield one table, while 1990 blocks yield one state at a time. The 1980 tract
    and BNA layers are both retained; accompanying county-outline layers are not tract records.
    Geometry stays in the source coordinate system and receives no repairs here.

    Use ``with closing(read_boundary_archive(...))`` from contextlib. Historical reading keeps the
    outer archive and a temporary directory open between yielded tables; closing releases them
    when a caller stops early or its processing fails.

    Args:
        archive_path (Path): Downloaded TIGER or NHGIS boundary ZIP.
        source_archive_relative_path (str): Original archive name relative to the raw-data
            directory.
        census_year (int): Census year: 1980, 1990, 2000, 2010, or 2020.
        geography_level (GeographyLevel): County or tract for 1980; county, tract, block group, or
            block for 1990–2020. Places are supported only for 2020.

    Yields:
        gpd.GeoDataFrame: Geographic ID, state and county codes, source pointers, correction and
            water-block flags, and geometry. County codes are missing for places, which can cross
            counties.

    Raises:
        ValueError: The year/level is unsupported, or layers, columns, identifiers, or coordinate
            information are invalid. Unsupported selections are rejected before reading files.
        OSError: An archive or temporary file cannot be read or written.
        zipfile.BadZipFile: An NHGIS archive cannot be opened. GDAL read errors also propagate.
    """
    if census_year in (2000, 2010, 2020):
        yield read_modern_tiger_boundaries(
            archive_path, source_archive_relative_path, census_year, geography_level
        )
        return

    if census_year not in (1980, 1990):
        raise ValueError(f"Unsupported boundary year: {census_year}")

    check_nhgis_boundary_selection(census_year, geography_level)

    with ZipFile(archive_path) as archive, TemporaryDirectory() as temporary_directory:
        inner_archive_names = sorted(
            name for name in archive.namelist() if name.lower().endswith(".zip")
        )

        if not inner_archive_names or (
            geography_level != GeographyLevel.BLOCK and len(inner_archive_names) != 1
        ):
            raise ValueError(
                "NHGIS boundaries require one national ZIP or separate state block ZIPs"
            )

        seen_block_states = set()

        for inner_archive_name in inner_archive_names:
            inner_archive_path = Path(temporary_directory) / "boundaries.zip"

            # Give the boundary reader a local path to the inner ZIP without unpacking its contents.
            with (
                archive.open(inner_archive_name) as source,
                inner_archive_path.open("wb") as destination,
            ):
                shutil.copyfileobj(source, destination)

            boundaries_df = read_nhgis_boundary_layers(
                inner_archive_path,
                source_archive_relative_path,
                inner_archive_name,
                census_year,
                geography_level,
            )

            if geography_level == GeographyLevel.BLOCK:
                state_codes = boundaries_df[GeographyColumn.STATE_CODE].unique()

                if len(state_codes) != 1 or state_codes[0] in seen_block_states:
                    raise ValueError("Each NHGIS block archive must describe a different state")

                seen_block_states.add(state_codes[0])

            yield boundaries_df


def check_nhgis_boundary_selection(census_year: int, geography_level: GeographyLevel) -> None:
    """Reject unsupported historical year/level pairs before reading or normalizing a table.

    Args:
        census_year (int): Historical Census year, 1980 or 1990.
        geography_level (GeographyLevel): County or tract for either year; block group and block
            are supported only for 1990.

    Raises:
        ValueError: The year and level do not identify a supported NHGIS boundary product.
    """
    selection = (census_year, geography_level)

    if selection not in NHGIS_NATIONAL_LAYER_NAMES and selection != (1990, GeographyLevel.BLOCK):
        raise ValueError(f"Unsupported NHGIS boundary selection: {census_year} {geography_level}")


def read_modern_tiger_boundaries(
    archive_path: Path,
    source_archive_relative_path: str,
    census_year: int,
    geography_level: GeographyLevel,
) -> gpd.GeoDataFrame:
    """Read one 2000–2020 TIGER layer and check its geographic ID against its component codes.

    Args:
        archive_path (Path): TIGER ZIP containing a single boundary layer.
        source_archive_relative_path (str): Archive name beneath the raw-data directory.
        census_year (int): 2000, 2010, or 2020.
        geography_level (GeographyLevel): County, tract, block group, or block; places use 2020.

    Returns:
        gpd.GeoDataFrame: Standard geographic columns and source pointers in the original CRS.

    Raises:
        ValueError: The year/level is unsupported, or layer count, columns, IDs, or coordinate
            information are invalid.
        OSError: The archive cannot be read. GDAL read errors also propagate.
    """
    try:
        column_suffix, geographic_id_column = TIGER_IDENTIFIER_COLUMNS[census_year, geography_level]
    except KeyError:
        raise ValueError(
            f"Unsupported modern TIGER boundary selection: {census_year} {geography_level}"
        ) from None

    component_columns = [(f"STATEFP{column_suffix}", 2)]

    if geography_level == GeographyLevel.PLACE:
        component_columns.append((f"PLACEFP{column_suffix}", 5))
    else:
        component_columns.append((f"COUNTYFP{column_suffix}", 3))

    if geography_level in (GeographyLevel.TRACT, GeographyLevel.BLOCK_GROUP, GeographyLevel.BLOCK):
        component_columns.append((f"TRACTCE{column_suffix}", 6))

    if geography_level == GeographyLevel.BLOCK_GROUP:
        component_columns.append((f"BLKGRPCE{column_suffix}", 1))
    elif geography_level == GeographyLevel.BLOCK:
        component_columns.append((f"BLOCKCE{column_suffix}", 4))

    archive_read_path = f"/vsizip/{archive_path.resolve()}"
    layer_metadata = pyogrio.list_layers(archive_read_path)

    if len(layer_metadata) != 1:
        raise ValueError("A TIGER boundary archive must contain exactly one layer")

    layer_name = layer_metadata[0][0]
    boundaries_df = pyogrio.read_dataframe(archive_read_path, layer=layer_name)
    required_columns = [
        geographic_id_column,
        *(component_column for component_column, _ in component_columns),
    ]

    check_boundary_columns_and_crs(boundaries_df, required_columns)

    expected_geographic_ids = pd.Series("", index=boundaries_df.index)

    for component_column, code_width in component_columns:
        if (
            not boundaries_df[component_column]
            .str.fullmatch(rf"[0-9]{{{code_width}}}", na=False)
            .all()
        ):
            raise ValueError(f"Invalid TIGER geographic component: {component_column}")

        expected_geographic_ids += boundaries_df[component_column]

    if not boundaries_df[geographic_id_column].eq(expected_geographic_ids).all():
        raise ValueError("TIGER geographic IDs disagree with their component codes")

    boundaries_df[GeographyColumn.GEOGRAPHIC_ID] = boundaries_df[geographic_id_column]
    boundaries_df[GeographyColumn.STATE_CODE] = boundaries_df[f"STATEFP{column_suffix}"]
    boundaries_df[GeographyColumn.COUNTY_CODE] = (
        None
        if geography_level == GeographyLevel.PLACE
        else boundaries_df[f"COUNTYFP{column_suffix}"]
    )

    return build_boundary_output(
        boundaries_df,
        source_archive_relative_path,
        f"{layer_name}.shp",
        boundaries_df[geographic_id_column],
    )


def read_nhgis_boundary_layers(
    inner_archive_path: Path,
    source_archive_relative_path: str,
    inner_archive_name: str,
    census_year: int,
    geography_level: GeographyLevel,
) -> gpd.GeoDataFrame:
    """Read the relevant layers from one NHGIS inner ZIP, normalizing each before combining.

    The BNA layer uses STATE80/COUNTY80 while the tract layer uses NHGISST/NHGISCTY. Normalizing
    their identifiers separately prevents unrelated source columns from becoming missing values
    when the layers are combined. The source GISJOIN remains available unchanged.

    Args:
        inner_archive_path (Path): Temporary copy of one inner boundary ZIP.
        source_archive_relative_path (str): Outer archive name beneath the raw-data directory.
        inner_archive_name (str): Inner ZIP's exact name inside that archive.
        census_year (int): 1980 or 1990.
        geography_level (GeographyLevel): County or tract for either year; block group and block
            are supported only for 1990.

    Returns:
        gpd.GeoDataFrame: Relevant layers with consistent columns and original geometry.

    Raises:
        ValueError: The year/level is unsupported, or layers, columns, identifiers, or coordinate
            systems are invalid.
        OSError: A layer cannot be read. GDAL read errors also propagate.
    """
    check_nhgis_boundary_selection(census_year, geography_level)

    archive_read_path = f"/vsizip/{inner_archive_path.resolve()}"
    available_layers = [str(name) for name, _ in pyogrio.list_layers(archive_read_path)]

    if geography_level == GeographyLevel.BLOCK:
        layer_names = [name for name in available_layers if name.endswith("_block_1990")]

        if len(layer_names) != 1:
            raise ValueError("Each historical block ZIP must contain one 1990 state block layer")

    else:
        layer_names = list(NHGIS_NATIONAL_LAYER_NAMES[census_year, geography_level])

    if not set(layer_names).issubset(available_layers):
        raise ValueError(
            f"Missing NHGIS boundary layers: {set(layer_names) - set(available_layers)}"
        )

    normalized_boundary_tables = []

    for layer_name in layer_names:
        boundaries_df = pyogrio.read_dataframe(archive_read_path, layer=layer_name)
        normalized_boundary_tables.append(
            normalize_nhgis_boundaries(
                boundaries_df,
                source_archive_relative_path,
                f"{inner_archive_name}/{layer_name}.shp",
                census_year,
                geography_level,
            )
        )

    if len(normalized_boundary_tables) == 1:
        return normalized_boundary_tables[0].reset_index(drop=True)

    if any(
        boundaries_df.crs != normalized_boundary_tables[0].crs
        for boundaries_df in normalized_boundary_tables
    ):
        raise ValueError("NHGIS layers have different coordinate systems")

    boundaries_df = gpd.GeoDataFrame(
        pd.concat(normalized_boundary_tables, ignore_index=True),
        crs=normalized_boundary_tables[0].crs,
    )

    check_boundary_identifiers(boundaries_df)

    return boundaries_df


def normalize_nhgis_boundaries(
    source_boundaries_df: gpd.GeoDataFrame,
    source_archive_relative_path: str,
    source_member_name: str,
    census_year: int,
    geography_level: GeographyLevel,
) -> gpd.GeoDataFrame:
    """Return checked NHGIS geography and correction notes.

    The returned table preserves the original GISJOIN in SOURCE_ID and uses corrected identifiers
    for joining. Geometry and its coordinate system are unchanged; source attributes not needed
    by the join remain in the raw archive.

    Args:
        source_boundaries_df (gpd.GeoDataFrame): One NHGIS source layer, left unchanged.
        source_archive_relative_path (str): Outer archive name beneath the raw-data directory.
        source_member_name (str): Inner ZIP and shapefile identifying the source layer.
        census_year (int): 1980 or 1990.
        geography_level (GeographyLevel): County or tract for either year; block group and block
            are supported only for 1990.

    Returns:
        gpd.GeoDataFrame: A separate table of geographic IDs, geometry, provenance, and flags.

    Raises:
        ValueError: The year/level is unsupported, or identifiers, components, or coordinate
            information disagree.
    """
    check_nhgis_boundary_selection(census_year, geography_level)
    check_boundary_columns_and_crs(source_boundaries_df, ["GISJOIN"])

    boundaries_df = source_boundaries_df.copy()
    boundaries_df[GeographyColumn.GEOGRAPHIC_ID] = boundaries_df["GISJOIN"]
    boundaries_df[BoundaryColumn.CORRECTION] = ""
    boundaries_df[BoundaryColumn.WATER_BLOCK] = False

    if geography_level in (GeographyLevel.BLOCK, GeographyLevel.BLOCK_GROUP):
        prepare_1990_block_and_block_group_fields_in_place(boundaries_df, geography_level)

    elif "BNA80" in boundaries_df:
        if census_year != 1980 or geography_level != GeographyLevel.TRACT:
            raise ValueError("BNA80 identifies a 1980 tract/BNA layer")

        check_1980_bna_codes(boundaries_df)

    else:
        check_boundary_columns_and_crs(boundaries_df, ["NHGISST", "NHGISCTY"])

    geographic_id_pattern = {
        GeographyLevel.COUNTY: r"G[0-9]{2}0[0-9]{3}0",
        GeographyLevel.TRACT: r"G[0-9]{2}0[0-9]{3}0(?:[0-9]{4}(?:[0-9]{2})?|nodata)",
        GeographyLevel.BLOCK_GROUP: r"G[0-9]{2}0[0-9]{3}0[0-9]{4}(?:[0-9]{2})?[0-9]",
        GeographyLevel.BLOCK: r"G[0-9]{2}0[0-9]{3}0[0-9]{4}(?:[0-9]{2})?[0-9]{3}[A-Za-z]?",
    }[geography_level]
    geographic_ids = boundaries_df[GeographyColumn.GEOGRAPHIC_ID]

    if not geographic_ids.str.fullmatch(geographic_id_pattern, na=False).all():
        raise ValueError("NHGIS geographic ID has an unexpected format")

    boundaries_df[GeographyColumn.STATE_CODE] = geographic_ids.str[1:3]
    boundaries_df[GeographyColumn.COUNTY_CODE] = geographic_ids.str[4:7]

    correct_kalawao_county_attribute_in_place(boundaries_df)
    check_nhgis_state_and_county_codes(boundaries_df)

    return build_boundary_output(
        boundaries_df,
        source_archive_relative_path,
        source_member_name,
        pd.Series(source_boundaries_df["GISJOIN"]),
    )


def check_1980_bna_codes(boundaries_df: gpd.GeoDataFrame) -> None:
    """Check that the 1980 block-numbering-area code agrees with the GISJOIN suffix.

    Args:
        boundaries_df (gpd.GeoDataFrame): BNA layer with GISJOIN, STATE80, COUNTY80, and BNA80.

    Raises:
        ValueError: A required field is missing, the coordinate system is absent, or BNA codes are
            malformed or disagree with GISJOIN.
    """
    check_boundary_columns_and_crs(boundaries_df, ["GISJOIN", "STATE80", "COUNTY80", "BNA80"])

    bna_codes = boundaries_df["BNA80"].astype("string").str.zfill(6)

    if not bna_codes.str.fullmatch(r"[0-9]{6}", na=False).all():
        raise ValueError("NHGIS BNA code must contain six digits")

    if not boundaries_df["GISJOIN"].str[8:].eq(bna_codes.str.replace(r"00$", "", regex=True)).all():
        raise ValueError("NHGIS BNA component disagrees with GISJOIN")


def check_nhgis_state_and_county_codes(boundaries_df: gpd.GeoDataFrame) -> None:
    """Compare available NHGIS state/county attributes with the normalized geographic codes.

    Args:
        boundaries_df (gpd.GeoDataFrame): Working table with normalized state and county columns.
            BNA attributes use FIPS codes; NHGISST/NHGISCTY add a trailing zero. Some 1990 block
            products have neither pair and are checked against FIPSSTCO during block preparation.

    Raises:
        ValueError: An available source pair disagrees with the normalized codes, a county field
            is missing, or the table lacks a coordinate system.
    """
    for state_column, county_column, code_suffix in (
        ("STATE80", "COUNTY80", ""),
        ("NHGISST", "NHGISCTY", "0"),
    ):
        if state_column not in boundaries_df:
            continue

        check_boundary_columns_and_crs(boundaries_df, [county_column])

        if (
            not pd.Series(boundaries_df[state_column])
            .eq(boundaries_df[GeographyColumn.STATE_CODE] + code_suffix)
            .all()
        ):
            raise ValueError("NHGIS state component disagrees with GISJOIN")

        if (
            not pd.Series(boundaries_df[county_column])
            .eq(boundaries_df[GeographyColumn.COUNTY_CODE] + code_suffix)
            .all()
        ):
            raise ValueError("NHGIS county component disagrees with GISJOIN")


def correct_kalawao_county_attribute_in_place(boundaries_df: gpd.GeoDataFrame) -> None:
    """Replace Kalawao's conflicting NHGIS county attribute and record the correction in place.

    GISJOIN identifies Kalawao (005), but the county attribute identifies Maui (009). The
    population record agrees with GISJOIN. See "Historical boundary corrections" in
    documentation/national_pipeline/data_processing_decisions_and_anomalies.md for the source
    correspondence.

    Args:
        boundaries_df (gpd.GeoDataFrame): Working NHGIS table with GEOID and a correction column.
            When NHGISCTY is present, only the known Kalawao value is replaced with "0050" and its
            correction note is set. Other source values remain for the ordinary checks.
    """
    if "NHGISCTY" not in boundaries_df:
        return

    kalawao_rows = boundaries_df[GeographyColumn.GEOGRAPHIC_ID].eq("G1500050") & boundaries_df[
        "NHGISCTY"
    ].eq("0090")

    boundaries_df.loc[kalawao_rows, "NHGISCTY"] = "0050"
    boundaries_df.loc[kalawao_rows, BoundaryColumn.CORRECTION] = "kalawao_county_from_gisjoin"


def prepare_1990_block_and_block_group_fields_in_place(
    boundaries_df: gpd.GeoDataFrame, geography_level: GeographyLevel
) -> None:
    """Check 1990 block and block-group identifiers, correcting known block errors in place.

    Blocks also receive Census IDs and water flags. Block groups undergo the same component
    checks but receive no block-specific corrections, Census-ID column, or water classification.
    The working table's GISJOIN column stays unchanged.

    Args:
        boundaries_df (gpd.GeoDataFrame): Working copy with GEOID initialized from GISJOIN and
            correction/water fields initialized. Known block errors change FIPSSTCO, STFID, or
            GEOID and record a correction note. Blocks also receive CENSUS_ID and WATER_BLOCK.
        geography_level (GeographyLevel): BLOCK or BLOCK_GROUP, checked by the NHGIS caller.

    Raises:
        ValueError: Required source columns or coordinate information are missing, geographic
            components disagree, or a known Alaska correction has unexpected components.
    """
    unit_column = "BLOCK" if geography_level == GeographyLevel.BLOCK else "GROUP"
    check_boundary_columns_and_crs(boundaries_df, ["FIPSSTCO", "TRACT", "STFID", unit_column])

    if geography_level == GeographyLevel.BLOCK:
        correct_known_1990_block_errors_in_place(boundaries_df)

    expected_census_ids = (
        boundaries_df["FIPSSTCO"] + boundaries_df["TRACT"] + boundaries_df[unit_column]
    )

    if not pd.Series(boundaries_df["STFID"]).eq(expected_census_ids).all():
        raise ValueError("NHGIS STFID disagrees with its geographic components")

    tract_codes = boundaries_df["TRACT"].str.replace(r"00$", "", regex=True)
    expected_geographic_ids = (
        "G"
        + boundaries_df["FIPSSTCO"].str[:2]
        + "0"
        + boundaries_df["FIPSSTCO"].str[2:]
        + "0"
        + tract_codes
        + boundaries_df[unit_column]
    )

    if (
        not pd.Series(boundaries_df[GeographyColumn.GEOGRAPHIC_ID])
        .eq(expected_geographic_ids)
        .all()
    ):
        raise ValueError("NHGIS GISJOIN disagrees with STFID components")

    if geography_level == GeographyLevel.BLOCK:
        boundaries_df[BoundaryColumn.CENSUS_ID] = boundaries_df["STFID"]

        # TIGER/Line 1999, Chapter 4, pp. 4-22–4-24: water numbers end in 99 with an optional
        # suffix A–Y. Z denotes ship crews and is not a water classification.
        # https://www2.census.gov/geo/tiger/TIGER1999/tiger99.pdf
        boundaries_df[BoundaryColumn.WATER_BLOCK] = boundaries_df["BLOCK"].str.fullmatch(
            r"[0-9]99[A-Ya-y]?", na=False
        )


def correct_known_1990_block_errors_in_place(boundaries_df: gpd.GeoDataFrame) -> None:
    """Apply the five verified Maryland, New Jersey, and Alaska block corrections in place.

    These are exact repairs, not a rule for resolving arbitrary disagreements. The Maryland county
    and New Jersey STFIDs follow the agreeing component codes, GISJOINs, and original STF1B
    records. Alaska's two malformed GISJOINs have intact Census IDs. See "Historical boundary
    corrections" in documentation/national_pipeline/data_processing_decisions_and_anomalies.md for
    the evidence. The caller checks that all identifiers agree after these repairs.

    Args:
        boundaries_df (gpd.GeoDataFrame): Working block table with source GISJOIN/FIPSSTCO/STFID,
            GEOID initialized from GISJOIN, and a correction column. Repairs change FIPSSTCO,
            STFID, GEOID, and correction notes only for the specified source records.

    Raises:
        ValueError: A known malformed Alaska GISJOIN has a different Census ID than expected.
    """
    maryland_rows = boundaries_df["GISJOIN"].eq("G24003709962558") & boundaries_df["FIPSSTCO"].eq(
        "24001"
    )

    boundaries_df.loc[maryland_rows, "FIPSSTCO"] = "24037"
    boundaries_df.loc[maryland_rows, BoundaryColumn.CORRECTION] = "maryland_1990_county_attribute"

    new_jersey_3714_rows = boundaries_df["GISJOIN"].eq("G34003703714301") & boundaries_df[
        "STFID"
    ].eq("34037037143301")

    boundaries_df.loc[new_jersey_3714_rows, "STFID"] = "34037371400301"
    boundaries_df.loc[new_jersey_3714_rows, BoundaryColumn.CORRECTION] = "new_jersey_1990_stfid"

    new_jersey_3711_rows = boundaries_df["GISJOIN"].eq("G34003703711103") & boundaries_df[
        "STFID"
    ].eq("34037037111103")

    boundaries_df.loc[new_jersey_3711_rows, "STFID"] = "34037371100103"
    boundaries_df.loc[new_jersey_3711_rows, BoundaryColumn.CORRECTION] = "new_jersey_1990_stfid"

    for source_geographic_id, corrected_geographic_id, expected_census_id in (
        ("G 0202800977149", "G02028009777149", "02280977700149"),
        ("G 0202800977165", "G02028009777165", "02280977700165"),
    ):
        alaska_rows = boundaries_df["GISJOIN"].eq(source_geographic_id)

        if not boundaries_df.loc[alaska_rows, "STFID"].eq(expected_census_id).all():
            raise ValueError("Known Alaska boundary correction has unexpected components")

        boundaries_df.loc[alaska_rows, GeographyColumn.GEOGRAPHIC_ID] = corrected_geographic_id
        boundaries_df.loc[alaska_rows, BoundaryColumn.CORRECTION] = "alaska_1990_gisjoin"


def check_boundary_columns_and_crs(
    boundaries_df: gpd.GeoDataFrame, required_columns: list[str]
) -> None:
    """Require source columns and a declared coordinate system.

    Args:
        boundaries_df (gpd.GeoDataFrame): Source or working boundary table to inspect.
        required_columns (list[str]): Column names needed for the next operation.

    Raises:
        ValueError: A named column is missing or the coordinate system is not declared.
    """
    missing_columns = set(required_columns) - set(boundaries_df.columns)

    if missing_columns:
        raise ValueError(f"Boundary source is missing columns: {sorted(missing_columns)}")

    if boundaries_df.crs is None:
        raise ValueError("Boundary source has no coordinate reference system")


def check_boundary_identifiers(boundaries_df: gpd.GeoDataFrame) -> None:
    """Reject empty layers, missing IDs, and duplicate IDs rather than merging their geometry."""
    geographic_ids = pd.Series(boundaries_df[GeographyColumn.GEOGRAPHIC_ID])

    if boundaries_df.empty or geographic_ids.isna().any() or geographic_ids.duplicated().any():
        raise ValueError("Boundary geographic IDs must be present and unique in a nonempty layer")


def build_boundary_output(
    boundaries_df: gpd.GeoDataFrame,
    source_archive_relative_path: str,
    source_member_name: str,
    source_geographic_ids: pd.Series,
) -> gpd.GeoDataFrame:
    """Check identifiers and build a separate output table with source locations and flags.

    Existing Census IDs, correction notes, and water flags are carried into the output. Absent
    fields default to empty text or False. A default water flag means no water classification
    was made, not that the feature was independently checked.

    Args:
        boundaries_df (gpd.GeoDataFrame): Working layer with normalized geography columns.
        source_archive_relative_path (str): Archive name relative to the raw-data directory.
        source_member_name (str): Shapefile name, including its inner ZIP for NHGIS.
        source_geographic_ids (pd.Series): Original identifiers, indexed like boundaries_df.

    Returns:
        gpd.GeoDataFrame: A copy containing only the fields used for joining and source
            accounting.

    Raises:
        ValueError: Geographic IDs are missing or repeated, or the source layer is empty.
    """
    check_boundary_identifiers(boundaries_df)

    geography_columns = [
        GeographyColumn.GEOGRAPHIC_ID,
        GeographyColumn.STATE_CODE,
        GeographyColumn.COUNTY_CODE,
        "geometry",
    ]
    output_df = boundaries_df[geography_columns].copy()

    output_df[BoundaryColumn.SOURCE_FILE] = source_archive_relative_path
    output_df[BoundaryColumn.SOURCE_MEMBER] = source_member_name
    output_df[BoundaryColumn.SOURCE_ID] = source_geographic_ids
    output_df[BoundaryColumn.CENSUS_ID] = boundaries_df.get(BoundaryColumn.CENSUS_ID, "")
    output_df[BoundaryColumn.CORRECTION] = boundaries_df.get(BoundaryColumn.CORRECTION, "")
    output_df[BoundaryColumn.WATER_BLOCK] = boundaries_df.get(BoundaryColumn.WATER_BLOCK, False)

    output_columns = [
        GeographyColumn.GEOGRAPHIC_ID,
        GeographyColumn.STATE_CODE,
        GeographyColumn.COUNTY_CODE,
        *BoundaryColumn,
        "geometry",
    ]

    return gpd.GeoDataFrame(output_df[output_columns], crs=boundaries_df.crs)
