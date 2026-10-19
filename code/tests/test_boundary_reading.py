"""Boundary reading preserves mixed historical layers and checks source identities."""

from contextlib import closing
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd
import pytest
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.join_geographies.read_boundaries import (
    BoundaryColumn,
    normalize_nhgis_boundaries,
    read_boundary_archive,
)
from shapely.geometry import box


def write_shape_zip(directory, layers):
    directory.mkdir()
    for name, boundaries_df in layers.items():
        boundaries_df.to_file(directory / f"{name}.shp", engine="pyogrio")
    zip_path = directory.with_suffix(".zip")
    with ZipFile(zip_path, "w") as archive:
        for member in directory.iterdir():
            archive.write(member, member.name)
    return zip_path


def make_boundaries(columns):
    return gpd.GeoDataFrame(
        columns,
        geometry=[
            box(index, 0, index + 1, 1) for index in range(len(next(iter(columns.values()))))
        ],
        crs="EPSG:4269",
    )


def test_1980_reader_keeps_bnas_and_tracts_but_excludes_county_context(tmp_path):
    layers = {
        "US_bna_1980": make_boundaries(
            {"GISJOIN": ["G01000509901"], "STATE80": ["01"], "COUNTY80": ["005"], "BNA80": [990100]}
        ),
        "US_tract_1980": make_boundaries(
            {"GISJOIN": ["G01000300001"], "NHGISST": ["010"], "NHGISCTY": ["0030"]}
        ),
        "US_tractcounty_1980": make_boundaries({"GISJOIN": ["G0100030"]}),
    }
    inner_zip = write_shape_zip(tmp_path / "shapes", layers)
    outer_zip = tmp_path / "outer.zip"
    with ZipFile(outer_zip, "w") as archive:
        archive.write(inner_zip, "extract/shapes.zip")

    with closing(
        read_boundary_archive(outer_zip, "nhgis/tracts.zip", 1980, GeographyLevel.TRACT)
    ) as tables:
        (boundaries_df,) = tables

    assert boundaries_df.GEOID.tolist() == ["G01000509901", "G01000300001"]
    assert boundaries_df.state.tolist() == ["01", "01"]
    assert boundaries_df.county.tolist() == ["005", "003"]
    assert boundaries_df[BoundaryColumn.SOURCE_ID].tolist() == boundaries_df.GEOID.tolist()
    assert boundaries_df[BoundaryColumn.SOURCE_MEMBER].tolist() == [
        "extract/shapes.zip/US_bna_1980.shp",
        "extract/shapes.zip/US_tract_1980.shp",
    ]
    assert boundaries_df.geometry.geom_equals(
        pd.concat([layers[name].geometry for name in list(layers)[:2]], ignore_index=True)
    ).all()
    assert boundaries_df.crs == layers["US_tract_1980"].crs


@pytest.mark.parametrize(
    "year,geography,id_column,components,geographic_id",
    [
        (
            2000,
            GeographyLevel.BLOCK_GROUP,
            "BKGPIDFP00",
            {"STATEFP00": "10", "COUNTYFP00": "001", "TRACTCE00": "040100", "BLKGRPCE00": "1"},
            "100010401001",
        ),
        (
            2010,
            GeographyLevel.TRACT,
            "GEOID10",
            {"STATEFP10": "10", "COUNTYFP10": "001", "TRACTCE10": "040100"},
            "10001040100",
        ),
        (
            2020,
            GeographyLevel.BLOCK,
            "GEOID20",
            {"STATEFP20": "10", "COUNTYFP20": "001", "TRACTCE20": "040100", "BLOCKCE20": "1001"},
            "100010401001001",
        ),
        (2020, GeographyLevel.PLACE, "GEOID", {"STATEFP": "10", "PLACEFP": "21200"}, "1021200"),
    ],
)
def test_modern_reader_uses_source_vintage_columns(
    tmp_path, year, geography, id_column, components, geographic_id
):
    columns = {column: [value] for column, value in components.items()}
    columns[id_column] = [geographic_id]
    archive_path = write_shape_zip(tmp_path / "shapes", {"boundary": make_boundaries(columns)})
    with closing(
        read_boundary_archive(archive_path, "tiger/shapes.zip", year, geography)
    ) as tables:
        (boundaries_df,) = tables
    assert boundaries_df.GEOID.tolist() == [geographic_id]
    assert boundaries_df.state.tolist() == ["10"]
    assert boundaries_df[BoundaryColumn.SOURCE_ID].tolist() == [geographic_id]
    assert not boundaries_df[BoundaryColumn.WATER_BLOCK].any()
    assert boundaries_df[BoundaryColumn.CENSUS_ID].eq("").all()
    if geography == GeographyLevel.PLACE:
        assert boundaries_df.county.isna().all()
    else:
        assert boundaries_df.county.tolist() == ["001"]


def test_historical_corrections_preserve_source_ids_and_require_known_components():
    blocks_df = make_boundaries(
        {
            "GISJOIN": ["G 0202800977149", "G 0202800977165", "G02028009777199A"],
            "FIPSSTCO": ["02280"] * 3,
            "TRACT": ["977700"] * 3,
            "BLOCK": ["149", "165", "199A"],
            "STFID": ["02280977700149", "02280977700165", "02280977700199A"],
        }
    )
    normalized_df = normalize_nhgis_boundaries(
        blocks_df.copy(), "blocks.zip", "AK.shp", 1990, GeographyLevel.BLOCK
    )
    assert normalized_df.GEOID.tolist() == [
        "G02028009777149",
        "G02028009777165",
        "G02028009777199A",
    ]
    assert normalized_df[BoundaryColumn.SOURCE_ID].tolist() == blocks_df.GISJOIN.tolist()
    assert normalized_df[BoundaryColumn.CENSUS_ID].tolist() == blocks_df.STFID.tolist()
    assert normalized_df[BoundaryColumn.WATER_BLOCK].tolist() == [False, False, True]
    assert normalized_df[BoundaryColumn.CORRECTION].ne("").tolist() == [True, True, False]

    blocks_df.loc[0, ["BLOCK", "STFID"]] = ["150", "02280977700150"]
    with pytest.raises(ValueError, match="unexpected components"):
        normalize_nhgis_boundaries(blocks_df, "blocks.zip", "AK.shp", 1990, GeographyLevel.BLOCK)

    county_df = make_boundaries({"GISJOIN": ["G1500050"], "NHGISST": ["150"], "NHGISCTY": ["0090"]})
    normalized_df = normalize_nhgis_boundaries(
        county_df, "counties.zip", "US.shp", 1980, GeographyLevel.COUNTY
    )
    assert normalized_df.county.tolist() == ["005"]
    assert normalized_df[BoundaryColumn.CORRECTION].tolist() == ["kalawao_county_from_gisjoin"]


def test_1990_metadata_repairs_use_agreeing_source_ids_without_changing_gisjoin():
    blocks_df = make_boundaries(
        {
            "GISJOIN": ["G24003709962558", "G34003703714301", "G34003703711103"],
            "FIPSSTCO": ["24001", "34037", "34037"],
            "TRACT": ["996200", "371400", "371100"],
            "BLOCK": ["558", "301", "103"],
            "STFID": ["24037996200558", "34037037143301", "34037037111103"],
        }
    )
    normalized_df = normalize_nhgis_boundaries(
        blocks_df.copy(), "blocks.zip", "source.shp", 1990, GeographyLevel.BLOCK
    )
    assert normalized_df.GEOID.tolist() == blocks_df.GISJOIN.tolist()
    assert normalized_df[BoundaryColumn.CENSUS_ID].tolist() == [
        "24037996200558",
        "34037371400301",
        "34037371100103",
    ]
    assert normalized_df.county.tolist() == ["037"] * 3
    assert normalized_df[BoundaryColumn.CORRECTION].ne("").all()

    blocks_df.loc[0, "TRACT"] = "996100"
    with pytest.raises(ValueError, match="STFID disagrees"):
        normalize_nhgis_boundaries(
            blocks_df, "blocks.zip", "source.shp", 1990, GeographyLevel.BLOCK
        )


@pytest.mark.parametrize("problem", ["duplicate", "wrong_county", "missing_crs"])
def test_historical_reader_rejects_inconsistent_boundary_metadata(problem):
    boundaries_df = make_boundaries(
        {"GISJOIN": ["G01000100001"], "NHGISST": ["010"], "NHGISCTY": ["0010"]}
    )
    if problem == "duplicate":
        boundaries_df = pd.concat([boundaries_df, boundaries_df], ignore_index=True)
    elif problem == "wrong_county":
        boundaries_df["NHGISCTY"] = "0030"
    else:
        boundaries_df = boundaries_df.set_crs(None, allow_override=True)
    with pytest.raises(ValueError):
        normalize_nhgis_boundaries(
            boundaries_df, "tracts.zip", "US.shp", 1980, GeographyLevel.TRACT
        )
