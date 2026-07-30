from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from pipeline.preprocessing.census_geographies import (
    is_original_tract_family_shapefile,
    nhgis_extract_dirs,
    read_census_population,
    read_nested_nhgis_shapefile,
    read_nhgis_1980_population,
    state_county_series,
    standardize_census_geography,
)


def test_original_tract_family_shapefile_names_are_accepted():
    assert is_original_tract_family_shapefile(Path("US_tract_1990.shp"), "1990")
    assert is_original_tract_family_shapefile(Path("US_bna_1990.shp"), "1990")


def test_conflated_and_nonmatching_shapefiles_are_rejected():
    assert not is_original_tract_family_shapefile(
        Path("US_tract_1990_conflated.shp"),
        "1990",
    )
    assert not is_original_tract_family_shapefile(
        Path("nhgis_shapefile_tl2008_us_tract_1990/US_tract_1990.shp"),
        "1990",
    )
    assert not is_original_tract_family_shapefile(Path("US_county_1990.shp"), "1990")
    assert not is_original_tract_family_shapefile(
        Path("US_tractcounty_1990.shp"),
        "1990",
    )
    assert not is_original_tract_family_shapefile(
        Path("US_county_tract_1990.shp"),
        "1990",
    )
    assert not is_original_tract_family_shapefile(Path("US_tract_1980.shp"), "1990")


def test_standardize_census_block_group_geography():
    gdf = gpd.GeoDataFrame(
        {
            "STATEFP10": ["1"],
            "COUNTYFP10": ["1"],
            "TRACTCE10": ["20100"],
            "BLKGRPCE10": ["2"],
        },
        geometry=[Point(0, 0)],
        crs="EPSG:4326",
    )

    standardized = standardize_census_geography(gdf, "block_groups")

    assert standardized.loc[0, "JOIN_KEY"] == "010010201002"
    assert standardized.loc[0, "GISJOIN"] == "G010010201002"
    assert standardized.loc[0, "STATEFP"] == "01"
    assert standardized.loc[0, "COUNTYFP"] == "001"


def test_1980_population_reader_sums_split_block_group_tables(tmp_path):
    df = pd.DataFrame(
        {
            "GISJOIN": ["G010001002011"],
            "STATEA": ["01"],
            "COUNTYA": ["001"],
            "C9DAA001": ["10"],
            "C9DAA002": ["3"],
            "C9DAA003": ["1"],
            "C9DAB001": ["20"],
            "C9DAB002": ["7"],
            "C9DAB003": ["2"],
            "C9GAA001": ["1"],
            "C9GAA002": ["0"],
            "C9GAB001": ["2"],
            "C9GAB002": ["1"],
        }
    )

    pop = read_nhgis_1980_population(df, tmp_path / "nhgis_1980_block_groups.csv")

    assert pop.loc[0, "WHITE"] == 27
    assert pop.loc[0, "BLACK"] == 9
    assert pop.loc[0, "TOTPOP"] == 43


def test_2000_population_reader_preserves_integer_and_decimal_tracts(tmp_path):
    df = pd.DataFrame(
        {
            "GEOID": ["060530001041", "060530001041"],
            "state": ["06", "06"],
            "county": ["053", "053"],
            "tract": ["000104", "0104"],
            "block group": ["1", "1"],
            "TOTPOP": ["3214", "3325"],
            "NH_WHITE": ["1279", "215"],
            "NH_BLACK": ["50", "24"],
        }
    )

    pop = read_census_population(
        df,
        tmp_path / "census_2000_block_groups.csv",
        2000,
        "block_groups",
    )

    assert pop["JOIN_KEY"].tolist() == ["060530001041", "060530104001"]
    assert not pop["JOIN_KEY"].duplicated().any()


def test_nhgis_geography_extract_dirs_prefer_year_level_directory(tmp_path):
    dirs = nhgis_extract_dirs(tmp_path, 1990, "block_groups")

    assert dirs == [
        tmp_path / "ipums_geography_extracts" / "1990" / "block_groups",
        tmp_path / "ipums_geography_extracts" / "1990",
    ]


def test_nested_nhgis_shapefile_uses_explicit_year_for_level_directory(tmp_path):
    shape_dir = tmp_path / "shape"
    inner_zip = tmp_path / "nhgis0046_shapefile_tl2000_us_blck_grp_1990.zip"
    outer_zip = (
        tmp_path
        / "ipums_geography_extracts"
        / "1990"
        / "block_groups"
        / "nhgis0046_shape.zip"
    )
    outer_zip.parent.mkdir(parents=True)

    gdf = gpd.GeoDataFrame(
        {"GISJOIN": ["G010001000101"], "NHGISST": ["01"], "NHGISCTY": ["001"]},
        geometry=[Point(0, 0)],
        crs="EPSG:4326",
    )
    shape_dir.mkdir()
    shp_path = shape_dir / "US_blck_grp_1990.shp"
    gdf.to_file(shp_path)

    import zipfile

    with zipfile.ZipFile(inner_zip, "w") as zf:
        for path in shape_dir.iterdir():
            zf.write(path, arcname=path.name)

    with zipfile.ZipFile(outer_zip, "w") as zf:
        zf.write(inner_zip, arcname=f"nhgis0046_shape/{inner_zip.name}")

    result = read_nested_nhgis_shapefile(outer_zip, 1990, "block_groups")

    assert result is not None
    assert result["GISJOIN"].tolist() == ["G010001000101"]


def test_state_county_series_reads_fipsstco():
    gdf = gpd.GeoDataFrame({"FIPSSTCO": ["02013"]}, geometry=[Point(0, 0)])

    state, county = state_county_series(gdf)

    assert state.tolist() == ["02"]
    assert county.tolist() == ["013"]
