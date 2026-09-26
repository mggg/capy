"""Apply documented 1980 population corrections and reconstruct missing BNA boundaries.

The Census correction is in Census Tracts, New York, N.Y.–N.J., section 1, printed page XII:
https://archive.org/details/1980censusofpo8022601unse
TIGER record layouts and the NAD27 coordinate system are described in the 1992 documentation:
https://assets.nhgis.org/original-data/gis/TIGER_1992_TechDoc.pdf
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd
import shapely

from capy_core.geography_types import GeographyLevel
from capy_core.population_table_columns import GeographyColumn, PopulationColumn
from capy_core.retrieve_data.census.build_published_file_requests import MISSING_1980_BNAS_BY_COUNTY
from capy_core.retrieve_data.nhgis.table_columns import Nhgis1980Column

from .read_boundaries import BoundaryColumn

if TYPE_CHECKING:
    from .select_inputs import GeographyJoinInputs

# These polygons belong to existing population records; merging them adds no population.
PARENT_GEOMETRY_MERGES_1980 = {
    "G3901370nodata": "G39013700303",  # Ottawa, Ohio
    "G3601070nodata": "G36010700207",  # Waverly, New York
    "G19005509902": "G19005509901",  # Dyersville, Iowa
    "G56000709902": "G56000709903",  # Hanna, Wyoming
}


# Transfer the complete original Richmond 0164 record, including every retained NT table cell.
# The published correction specifies the destination and 92 people, not revised race counts.
RICHMOND_0164_SOURCE_COUNTS = {
    Nhgis1980Column.TOTAL: 92,
    Nhgis1980Column.WHITE: 89,
    Nhgis1980Column.BLACK: 0,
    Nhgis1980Column.AMERICAN_INDIAN: 0,
    Nhgis1980Column.ESKIMO: 0,
    Nhgis1980Column.ALEUT: 0,
    Nhgis1980Column.JAPANESE: 0,
    Nhgis1980Column.CHINESE: 0,
    Nhgis1980Column.FILIPINO: 3,
    Nhgis1980Column.KOREAN: 0,
    Nhgis1980Column.ASIAN_INDIAN: 0,
    Nhgis1980Column.VIETNAMESE: 0,
    Nhgis1980Column.HAWAIIAN: 0,
    Nhgis1980Column.GUAMANIAN: 0,
    Nhgis1980Column.SAMOAN: 0,
    Nhgis1980Column.OTHER_RACE: 0,
    Nhgis1980Column.HISPANIC_TOTAL: 1,
    Nhgis1980Column.HISPANIC_WHITE: 1,
    Nhgis1980Column.HISPANIC_BLACK: 0,
    Nhgis1980Column.HISPANIC_INDIGENOUS_ASIAN_PACIFIC_ISLANDER: 0,
    Nhgis1980Column.HISPANIC_OTHER_RACE: 0,
}


def correct_richmond_population_1980(
    population_df: pd.DataFrame, geography_inputs: GeographyJoinInputs
) -> pd.DataFrame:
    """Transfer Richmond tract 0164's population to Kings in a copy of the 1980 table.

    Tract processing combines the two records and removes the invalid Richmond record. County
    processing transfers the same counts between Richmond and Kings. Other levels and states
    are unchanged. All source population cells and study counts receive the same correction.

    SOURCE_* columns continue to identify the destination's original record. The added
    POPULATION_CORRECTION note identifies the transferred source; corrected count cells must
    not be interpreted as verbatim values from that original row. Input tables remain unchanged.

    Args:
        population_df (pd.DataFrame): Processed records whose metadata matches the selection.
            The joining stage checks that contract before applying corrections.
        geography_inputs (GeographyJoinInputs): Year and level of the table. Only 1980 counties and
            tracts containing New York records receive this correction.

    Returns:
        pd.DataFrame: Corrected copy with a note on each changed record, or the unchanged input
            when the year, level, or state is outside this correction.

    Raises:
        ValueError: An affected record is missing, repeated, already corrected, or inconsistent
            with the source correction, or a county subtraction would produce a negative count.
        KeyError: A required geographic or count column is missing.
    """
    geography_level = geography_inputs.geography_level

    if geography_inputs.census_year != 1980 or geography_level not in (
        GeographyLevel.COUNTY,
        GeographyLevel.TRACT,
    ):
        return population_df

    if not bool(population_df[GeographyColumn.STATE_CODE].eq("36").any()):
        return population_df

    corrected_population_df = population_df.copy()

    richmond_geographic_id, kings_geographic_id = "G3600850", "G3600470"

    if geography_level == GeographyLevel.TRACT:
        richmond_geographic_id += "0164"
        kings_geographic_id += "0164"

    richmond_rows = corrected_population_df[GeographyColumn.GEOGRAPHIC_ID].eq(
        richmond_geographic_id
    )
    kings_rows = corrected_population_df[GeographyColumn.GEOGRAPHIC_ID].eq(kings_geographic_id)

    if richmond_rows.sum() != 1 or kings_rows.sum() != 1:
        raise ValueError("The Richmond correction requires one Richmond and one Kings record")

    if "POPULATION_CORRECTION" not in corrected_population_df:
        corrected_population_df["POPULATION_CORRECTION"] = ""

    if (
        corrected_population_df.loc[richmond_rows | kings_rows, "POPULATION_CORRECTION"]
        .ne("")
        .any()
    ):
        raise ValueError("The Richmond population correction has already been applied")

    transfer_counts = {
        **RICHMOND_0164_SOURCE_COUNTS,
        PopulationColumn.TOTAL: 92,
        PopulationColumn.NON_HISPANIC_WHITE: 88,
        PopulationColumn.NON_HISPANIC_BLACK: 0,
        PopulationColumn.POC: 4,
    }

    for population_column, transfer_count in transfer_counts.items():
        richmond_count = corrected_population_df.loc[richmond_rows, population_column].iloc[0]

        if geography_level == GeographyLevel.TRACT and richmond_count != transfer_count:
            raise ValueError(f"Richmond 0164 {population_column} differs from the original record")

        if richmond_count < transfer_count:
            raise ValueError(f"Richmond {population_column} cannot supply the documented transfer")

        corrected_population_df.loc[kings_rows, population_column] += transfer_count
        corrected_population_df.loc[richmond_rows, population_column] -= transfer_count

    remaining_white_black_counts = (
        corrected_population_df[PopulationColumn.NON_HISPANIC_WHITE]
        + corrected_population_df[PopulationColumn.NON_HISPANIC_BLACK]
    )

    if remaining_white_black_counts.gt(corrected_population_df[PopulationColumn.TOTAL]).any():
        raise ValueError("Richmond transfer leaves inconsistent White and Black population counts")

    corrected_population_df.loc[richmond_rows | kings_rows, "POPULATION_CORRECTION"] = (
        "1980 Census correction: transfer all counts from G36008500164 to G36004700164"
    )

    if geography_level == GeographyLevel.TRACT:
        corrected_population_df = corrected_population_df.loc[~richmond_rows].copy()

    return corrected_population_df.reset_index(drop=True)


def reconstruct_missing_1980_bnas(tiger_1992_directory: Path) -> gpd.GeoDataFrame:
    """Build the twelve omitted 1980 BNA polygons from five original TIGER1992 county ZIPs.

    Record type 1 gives chain endpoints, type 2 gives intervening vertices, and type 3 gives
    the 1980 areas on the left and right. Only chains separating a BNA from another area form
    its outline. Source coordinates use NAD27; population is joined separately by GEOID.

    Args:
        tiger_1992_directory (Path): Folder containing 12107.zip, 38033.zip, 40023.zip, 49021.zip,
            and 49025.zip, in their original published format.

    Returns:
        gpd.GeoDataFrame: GEOID, state, county, geometry in EPSG:4267, and source/correction
            columns. Every result is a nonempty valid polygon or multipolygon.

    Raises:
        OSError: A county archive cannot be read.
        BadZipFile: An archive is damaged.
        ValueError: Records, chain identities, closed outlines, or left/right assignments disagree.
        KeyError: A required record-type member is absent from an archive.
    """
    boundary_records = []

    for state_county_code, bna_codes in MISSING_1980_BNAS_BY_COUNTY.items():
        archive_path = tiger_1992_directory / f"{state_county_code}.zip"
        chains_df = read_1980_chains_from_tiger1992(archive_path, state_county_code)

        for bna_code in bna_codes:
            geographic_id = f"G{state_county_code[:2]}0{state_county_code[2:]}0{bna_code}"
            bna_outline = build_1980_bna_outline(chains_df, geographic_id)

            boundary_records.append(
                {
                    GeographyColumn.GEOGRAPHIC_ID: geographic_id,
                    GeographyColumn.STATE_CODE: state_county_code[:2],
                    GeographyColumn.COUNTY_CODE: state_county_code[2:],
                    "geometry": bna_outline,
                    BoundaryColumn.SOURCE_ID: geographic_id,
                    BoundaryColumn.CENSUS_ID: "",
                    BoundaryColumn.WATER_BLOCK: False,
                    BoundaryColumn.SOURCE_FILE: archive_path.as_posix(),
                    BoundaryColumn.SOURCE_MEMBER: ";".join(
                        f"TGR{state_county_code}.F5{record_type}" for record_type in (1, 2, 3)
                    ),
                    BoundaryColumn.CORRECTION: "1980 BNA reconstructed from 1992 TIGER chains",
                }
            )

    return gpd.GeoDataFrame(boundary_records, crs="EPSG:4267")


def read_1980_chains_from_tiger1992(archive_path: Path, state_county_code: str) -> gpd.GeoDataFrame:
    """Read directed chains and their original 1980 left/right geographic identifiers.

    Args:
        archive_path (Path): Original TIGER1992 county ZIP.
        state_county_code (str): Five-digit state/county code identifying its record filenames.

    Returns:
        gpd.GeoDataFrame: One line per chain, with left/right GISJOINs and NAD27 coordinates.

    Raises:
        OSError: Reading the ZIP fails.
        BadZipFile: The ZIP is damaged.
        KeyError: A required record member is absent.
        ValueError: Record lengths, identifiers, or vertex sequences disagree.
    """
    with ZipFile(archive_path) as archive:
        endpoint_records = read_tiger_records(
            archive, member_name=f"TGR{state_county_code}.F51", record_width=228
        )
        vertex_records = read_tiger_records(
            archive, member_name=f"TGR{state_county_code}.F52", record_width=208
        )
        area_records = read_tiger_records(
            archive, member_name=f"TGR{state_county_code}.F53", record_width=111
        )

    vertex_records_by_chain = defaultdict(list)

    for record in vertex_records:
        chain_id, sequence_number = int(record[5:15]), int(record[15:18])
        vertices = [
            decode_tiger_coordinate(record, coordinate_byte_offset=coordinate_byte_offset)
            for coordinate_byte_offset in range(18, 208, 19)
        ]

        vertex_records_by_chain[chain_id].append(
            (sequence_number, [point for point in vertices if point != (0, 0)])
        )

    geographic_ids_by_chain = {}

    for record in area_records:
        chain_id = int(record[5:15])

        if chain_id in geographic_ids_by_chain:
            raise ValueError(f"Repeated TIGER area record for chain {chain_id}")

        geographic_ids_by_chain[chain_id] = (
            build_tiger_1980_geographic_id(
                record, state_byte_offset=15, county_byte_offset=19, tract_byte_offset=45
            ),
            build_tiger_1980_geographic_id(
                record, state_byte_offset=17, county_byte_offset=22, tract_byte_offset=51
            ),
        )

    chain_records = []

    for record in endpoint_records:
        chain_id = int(record[5:15])
        ordered_vertex_records = sorted(vertex_records_by_chain.pop(chain_id, []))
        sequence_numbers = [sequence_number for sequence_number, _ in ordered_vertex_records]

        if sequence_numbers != list(range(1, len(ordered_vertex_records) + 1)):
            raise ValueError(f"Missing or repeated TIGER vertex sequence for chain {chain_id}")

        if chain_id not in geographic_ids_by_chain:
            raise ValueError(f"Missing or repeated TIGER chain {chain_id}")

        left_geographic_id, right_geographic_id = geographic_ids_by_chain.pop(chain_id)
        coordinates = [decode_tiger_coordinate(record, coordinate_byte_offset=190)]
        coordinates.extend(point for _, vertices in ordered_vertex_records for point in vertices)
        coordinates.append(decode_tiger_coordinate(record, coordinate_byte_offset=209))

        chain_records.append(
            {
                "left": left_geographic_id,
                "right": right_geographic_id,
                "geometry": shapely.LineString(coordinates),
            }
        )

    if geographic_ids_by_chain or vertex_records_by_chain:
        raise ValueError("TIGER area or vertex records have no corresponding endpoint record")

    return gpd.GeoDataFrame(chain_records, crs="EPSG:4267")


def read_tiger_records(archive: ZipFile, member_name: str, record_width: int) -> list[bytes]:
    """Read a TIGER file inside an open ZIP and check each nonblank record's size and type.

    Args:
        archive (ZipFile): Open county archive. The caller remains responsible for closing it.
        member_name (str): Exact filename within the ZIP, ending in its one-digit record type.
        record_width (int): Required number of bytes per record, excluding line endings.

    Returns:
        list[bytes]: Nonblank records without line endings. Individual fields are not checked;
            an empty file returns an empty list.

    Raises:
        KeyError: The named file is absent from the ZIP.
        OSError: Reading the file fails.
        BadZipFile: The ZIP is damaged.
        ValueError: A record has the wrong width or type.
    """
    records = [record for record in archive.read(member_name).splitlines() if record.strip()]
    record_type = member_name[-1:].encode("ascii")

    if any(len(record) != record_width or record[:1] != record_type for record in records):
        raise ValueError(f"Invalid TIGER records in {member_name}")

    return records


def decode_tiger_coordinate(record: bytes, coordinate_byte_offset: int) -> tuple[float, float]:
    """Convert a TIGER longitude/latitude pair from signed millionths of a degree to degrees.

    Args:
        record (bytes): Type-1 or type-2 record whose overall width was already checked.
        coordinate_byte_offset (int): Zero-based start of the ten-byte longitude field,
            immediately followed by the nine-byte latitude field.

    Returns:
        tuple[float, float]: Longitude and latitude in the source coordinate system, NAD27.
            Coordinate ranges are not checked. The caller removes unused (0, 0) vertex slots.

    Raises:
        ValueError: Either coordinate field cannot be read as an integer.
    """
    longitude = int(record[coordinate_byte_offset : coordinate_byte_offset + 10]) / 1_000_000
    latitude = int(record[coordinate_byte_offset + 10 : coordinate_byte_offset + 19]) / 1_000_000

    return longitude, latitude


def build_tiger_1980_geographic_id(
    record: bytes, state_byte_offset: int, county_byte_offset: int, tract_byte_offset: int
) -> str:
    """Form a 1980 GISJOIN from one side of a TIGER type-3 record.

    Args:
        record (bytes): Type-3 record whose overall width was already checked.
        state_byte_offset (int): Zero-based start of the two-byte state code.
        county_byte_offset (int): Zero-based start of the three-byte county code.
        tract_byte_offset (int): Zero-based start of the six-byte tract/BNA field.

    Returns:
        str: GISJOIN with surrounding field spaces removed, or an empty string if any field
            is blank. Code contents are preserved without numeric validation or normalization.

    Raises:
        UnicodeDecodeError: A geographic field contains non-ASCII bytes.
    """
    state_code = record[state_byte_offset : state_byte_offset + 2].decode("ascii").strip()
    county_code = record[county_byte_offset : county_byte_offset + 3].decode("ascii").strip()
    tract_code = record[tract_byte_offset : tract_byte_offset + 6].decode("ascii").strip()

    if not state_code or not county_code or not tract_code:
        return ""

    return f"G{state_code}0{county_code}0{tract_code}"


def build_1980_bna_outline(chains_df: gpd.GeoDataFrame, geographic_id: str) -> shapely.Geometry:
    """Build a closed BNA outline and verify that its interior agrees with chain directions.

    The side check samples either side of each chain's longest segment at its midpoint,
    away from the vertices where adjoining segments meet. The sampling distance is at most
    1% of the segment length and 1e-8 degrees, keeping it below the source's 1e-6-degree
    coordinate precision. This is a local consistency check, not a check along the whole chain
    or a geographic accuracy tolerance.

    Args:
        chains_df (gpd.GeoDataFrame): Directed TIGER chains with left/right 1980 GISJOINs.
        geographic_id (str): BNA identity to reconstruct.

    Returns:
        shapely.Geometry: Valid polygon or multipolygon, including any holes.

    Raises:
        ValueError: Chains are missing, do not close, or place the BNA on the wrong side.
    """
    boundary_chains_df = chains_df.loc[
        chains_df.left.eq(geographic_id) ^ chains_df.right.eq(geographic_id)
    ]

    if boundary_chains_df.empty:
        raise ValueError(f"No TIGER boundary chains for {geographic_id}")

    _, cuts, dangles, invalid_rings = shapely.polygonize_full(
        boundary_chains_df.geometry.to_numpy()
    )
    bna_outline = shapely.build_area(shapely.MultiLineString(boundary_chains_df.geometry.tolist()))

    if (
        any(not remainder.is_empty for remainder in (cuts, dangles, invalid_rings))
        or bna_outline.is_empty
        or not bna_outline.is_valid
        or bna_outline.geom_type not in ("Polygon", "MultiPolygon")
    ):
        raise ValueError(f"TIGER chains do not form a valid closed outline for {geographic_id}")

    for chain in boundary_chains_df.itertuples():
        segments = zip(chain.geometry.coords[:-1], chain.geometry.coords[1:])
        segment_start, segment_end = max(
            segments, key=lambda segment: shapely.LineString(segment).length
        )
        dx, dy = segment_end[0] - segment_start[0], segment_end[1] - segment_start[1]
        segment_length_degrees = (dx * dx + dy * dy) ** 0.5

        if segment_length_degrees == 0:
            raise ValueError(f"TIGER boundary has a zero-length chain for {geographic_id}")

        probe_offset_degrees = min(segment_length_degrees / 100, 1e-8)
        midpoint = (
            (segment_start[0] + segment_end[0]) / 2,
            (segment_start[1] + segment_end[1]) / 2,
        )

        # The perpendicular direction (-dy, dx) points left along the directed segment.
        left_probe = shapely.Point(
            midpoint[0] - dy / segment_length_degrees * probe_offset_degrees,
            midpoint[1] + dx / segment_length_degrees * probe_offset_degrees,
        )
        right_probe = shapely.Point(
            midpoint[0] + dy / segment_length_degrees * probe_offset_degrees,
            midpoint[1] - dx / segment_length_degrees * probe_offset_degrees,
        )

        if bna_outline.contains(left_probe) != (chain.left == geographic_id) or (
            bna_outline.contains(right_probe) != (chain.right == geographic_id)
        ):
            raise ValueError(f"TIGER chain sides disagree with the outline for {geographic_id}")

    return bna_outline
