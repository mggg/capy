"""Boundary preparation preserves caller-owned tables and rejects unsupported products early."""

from contextlib import closing

import geopandas as gpd
import pytest
from capy_core.geography_types import GeographyLevel
from capy_core.join_geographies.read_boundaries import (
    BoundaryColumn,
    build_boundary_output,
    normalize_nhgis_boundaries,
    read_boundary_archive,
)
from geopandas.testing import assert_geodataframe_equal
from shapely.geometry import box


def test_historical_corrections_leave_input_unchanged_on_success_and_failure():
    source_df = gpd.GeoDataFrame(
        {
            "GISJOIN": ["G24003709962558"],
            "FIPSSTCO": ["24001"],
            "TRACT": ["996200"],
            "BLOCK": ["558"],
            "STFID": ["24037996200558"],
        },
        geometry=[box(0, 0, 1, 1)],
        crs="EPSG:4269",
    )
    original_df = source_df.copy()

    normalized_df = normalize_nhgis_boundaries(
        source_df, "blocks.zip", "MD.shp", 1990, GeographyLevel.BLOCK
    )

    assert_geodataframe_equal(source_df, original_df)
    assert normalized_df.county.tolist() == ["037"]
    assert normalized_df[BoundaryColumn.CORRECTION].tolist() == ["maryland_1990_county_attribute"]

    source_df.loc[0, "TRACT"] = "996100"
    invalid_source_df = source_df.copy()

    with pytest.raises(ValueError, match="STFID disagrees"):
        normalize_nhgis_boundaries(source_df, "blocks.zip", "MD.shp", 1990, GeographyLevel.BLOCK)

    assert_geodataframe_equal(source_df, invalid_source_df)


def test_output_builder_adds_provenance_and_defaults_only_to_its_result():
    boundaries_df = gpd.GeoDataFrame(
        {"GEOID": ["10001040100"], "state": ["10"], "county": ["001"]},
        geometry=[box(0, 0, 1, 1)],
        crs="EPSG:4269",
    )
    original_df = boundaries_df.copy()

    output_df = build_boundary_output(boundaries_df, "tracts.zip", "DE.shp", boundaries_df.GEOID)

    assert_geodataframe_equal(boundaries_df, original_df)
    assert output_df[BoundaryColumn.SOURCE_FILE].tolist() == ["tracts.zip"]
    assert output_df[BoundaryColumn.SOURCE_MEMBER].tolist() == ["DE.shp"]
    assert output_df[BoundaryColumn.SOURCE_ID].tolist() == boundaries_df.GEOID.tolist()
    assert output_df[BoundaryColumn.CENSUS_ID].tolist() == [""]
    assert output_df[BoundaryColumn.CORRECTION].tolist() == [""]
    assert output_df[BoundaryColumn.WATER_BLOCK].tolist() == [False]


@pytest.mark.parametrize(
    "census_year,geography_level",
    [
        (1980, GeographyLevel.BLOCK_GROUP),
        (1980, GeographyLevel.BLOCK),
        (1990, GeographyLevel.PLACE),
        (2000, GeographyLevel.PLACE),
        (2020, GeographyLevel.STATE),
    ],
)
def test_unsupported_boundary_selection_fails_before_opening_file(
    tmp_path, census_year, geography_level
):
    with (
        closing(
            read_boundary_archive(
                tmp_path / "absent.zip", "absent.zip", census_year, geography_level
            )
        ) as boundary_tables,
        pytest.raises(ValueError, match="Unsupported .* boundary selection"),
    ):
        next(boundary_tables)
