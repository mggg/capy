"""Check historical repairs against original count cells and small directed TIGER outlines."""

from dataclasses import replace
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd
import pytest
import shapely
from capy_core.geography_types import GeographyLevel
from capy_core.join_geographies.repair_1980_sources import (
    MISSING_1980_BNAS_BY_COUNTY,
    build_1980_bna_outline,
    correct_richmond_population_1980,
    reconstruct_missing_1980_bnas,
)
from capy_core.join_geographies.select_inputs import GeographyJoinInputs
from capy_core.process_population.nhgis_columns import Nhgis1980Column


@pytest.mark.parametrize("geography_level", [GeographyLevel.TRACT, GeographyLevel.COUNTY])
def test_richmond_transfer_preserves_every_population_component_and_source_table(geography_level):
    # Independently transcribed nonzero cells from the original Richmond tract record.
    richmond_counts = dict.fromkeys([column.value for column in Nhgis1980Column], 0)
    richmond_counts.update(C7L001=92, C9D001=89, C9D008=3, C9F001=1, C9G001=1)
    richmond_counts.update(TOTPOP=92, WHITE=88, BLACK=0, POC=4)

    kings_counts = dict(richmond_counts)
    kings_counts.update(C7L001=1000, C9D001=1000, C9D008=0, C9F001=0, C9G001=0)
    kings_counts.update(TOTPOP=1000, WHITE=1000, BLACK=0, POC=0)

    tract_suffix = "0164" if geography_level == GeographyLevel.TRACT else ""
    population_df = pd.DataFrame(
        [
            {**richmond_counts, "GEOID": "G3600850" + tract_suffix, "SOURCE_ROW": 7},
            {**kings_counts, "GEOID": "G3600470" + tract_suffix, "SOURCE_ROW": 8},
        ]
    ).assign(state="36", CENSUS_YEAR=1980, SOURCE_FILE="original.zip")
    original_population_df = population_df.copy(deep=True)

    selection = GeographyJoinInputs(1980, geography_level, {}, {})
    later_selection = replace(selection, census_year=1990)
    later_population_df = population_df.assign(CENSUS_YEAR=1990)
    assert (
        correct_richmond_population_1980(later_population_df, later_selection)
        is later_population_df
    )

    corrected_population_df = correct_richmond_population_1980(population_df, selection)

    count_columns = list(richmond_counts)
    pd.testing.assert_series_equal(
        original_population_df[count_columns].sum(), corrected_population_df[count_columns].sum()
    )
    pd.testing.assert_frame_equal(population_df, original_population_df)

    kings_record = corrected_population_df.loc[
        corrected_population_df.GEOID.eq("G3600470" + tract_suffix)
    ].iloc[0]

    assert kings_record.TOTPOP == 1092 and kings_record.WHITE == 1088 and kings_record.POC == 4
    assert kings_record.C9D008 == 3 and kings_record.C9F001 == 1 and kings_record.C9G001 == 1
    assert kings_record.SOURCE_ROW == 8 and "G36008500164" in kings_record.POPULATION_CORRECTION
    assert len(corrected_population_df) == (1 if geography_level == GeographyLevel.TRACT else 2)

    with pytest.raises(ValueError):
        correct_richmond_population_1980(corrected_population_df, selection)


def write_tiger_county(output_directory, state_county_code, bna_codes, invalid_sequence=False):
    """Write square chains using the actual type-1/2/3 record widths and field positions."""
    records_by_type = {1: [], 2: [], 3: []}

    for chain_id, bna_code in enumerate(bna_codes, start=1):
        longitude, latitude = -81 + chain_id * 2, 30

        endpoint_record = bytearray(b" " * 228)
        endpoint_record[0:1] = b"1"
        endpoint_record[5:15] = f"{chain_id:10d}".encode()
        endpoint_coordinates = f"{longitude * 1_000_000:+010d}{latitude * 1_000_000:+09d}".encode()
        endpoint_record[190:209] = endpoint_coordinates
        endpoint_record[209:228] = endpoint_coordinates
        records_by_type[1].append(bytes(endpoint_record))

        vertex_record = bytearray(b" " * 208)
        vertex_record[0:1] = b"2"
        vertex_record[5:15] = f"{chain_id:10d}".encode()
        vertex_record[15:18] = b"  2" if invalid_sequence else b"  1"

        points = [
            (longitude + 1, latitude),
            (longitude + 1, latitude + 1),
            (longitude, latitude + 1),
        ]
        points.extend([(0, 0)] * 7)

        for position, (x, y) in enumerate(points):
            coordinate_byte_offset = 18 + position * 19
            vertex_record[coordinate_byte_offset : coordinate_byte_offset + 19] = (
                f"{x * 1_000_000:+010d}{y * 1_000_000:+09d}".encode()
            )

        records_by_type[2].append(bytes(vertex_record))

        area_record = bytearray(b" " * 111)
        area_record[0:1] = b"3"
        area_record[5:15] = f"{chain_id:10d}".encode()
        area_record[15:17], area_record[19:22] = (
            state_county_code[:2].encode(),
            state_county_code[2:].encode(),
        )
        area_record[45:51] = f"{bna_code:6s}".encode()
        records_by_type[3].append(bytes(area_record))

    with ZipFile(output_directory / f"{state_county_code}.zip", "w") as archive:
        for record_type, records in records_by_type.items():
            archive.writestr(f"TGR{state_county_code}.F5{record_type}", b"\r\n".join(records))


def test_reconstruction_reads_original_chain_vertices_and_preserves_bna_identity(tmp_path):
    for state_county_code, bna_codes in MISSING_1980_BNAS_BY_COUNTY.items():
        write_tiger_county(tmp_path, state_county_code, bna_codes)

    boundaries_df = reconstruct_missing_1980_bnas(tmp_path)

    assert len(boundaries_df) == 12 and boundaries_df.GEOID.is_unique
    assert boundaries_df.is_valid.all() and boundaries_df.crs.to_epsg() == 4267

    first_boundary = boundaries_df.iloc[0]

    assert (
        first_boundary.GEOID == "G12010709901"
        and first_boundary.state == "12"
        and first_boundary.county == "107"
    )
    assert first_boundary.geometry.equals(shapely.box(-79, 30, -78, 31))
    assert first_boundary.BOUNDARY_SOURCE_MEMBER == "TGR12107.F51;TGR12107.F52;TGR12107.F53"


def test_reconstruction_rejects_missing_shape_vertex_sequence(tmp_path):
    write_tiger_county(tmp_path, "12107", ("9901",), invalid_sequence=True)

    with pytest.raises(ValueError, match="vertex sequence"):
        reconstruct_missing_1980_bnas(tmp_path)


def test_reconstruction_preserves_holes_and_checks_which_side_contains_the_bna():
    outer_ring = shapely.LineString([(0, 0), (3, 0), (3, 3), (0, 3), (0, 0)])
    inner_ring = shapely.LineString([(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)])
    chains_df = gpd.GeoDataFrame(
        {"left": ["bna", "other"], "right": ["other", "bna"]},
        geometry=[outer_ring, inner_ring],
        crs="EPSG:4267",
    )

    outline = build_1980_bna_outline(chains_df, "bna")

    assert outline.equals(shapely.Polygon(outer_ring.coords, [inner_ring.coords]))

    chains_df.loc[1, ["left", "right"]] = ["bna", "other"]

    with pytest.raises(ValueError, match="chain sides disagree"):
        build_1980_bna_outline(chains_df, "bna")
