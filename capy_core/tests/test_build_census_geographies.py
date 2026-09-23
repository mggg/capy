from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from capy_core.preprocessing.build_census_geographies import (
    is_original_tract_family_shapefile,
    load_nhgis_geography,
    read_nested_nhgis_shapefile,
    standardize_census_geography,
    state_county_series,
)
from capy_core.preprocessing.population_tables import (
    parse_census_population,
    parse_nhgis_1980_population,
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
    geography_gdf = gpd.GeoDataFrame(
        {
            "STATEFP10": ["1"],
            "COUNTYFP10": ["1"],
            "TRACTCE10": ["20100"],
            "BLKGRPCE10": ["2"],
        },
        geometry=[Point(0, 0)],
        crs="EPSG:4326",
    )

    standardized_geography_gdf = standardize_census_geography(
        geography_gdf, "block_groups"
    )

    assert standardized_geography_gdf.loc[0, "JOIN_KEY"] == "010010201002"
    assert standardized_geography_gdf.loc[0, "GISJOIN"] == "G010010201002"
    assert standardized_geography_gdf.loc[0, "STATEFP"] == "01"
    assert standardized_geography_gdf.loc[0, "COUNTYFP"] == "001"


def test_1980_population_reader_sums_split_block_group_tables(tmp_path):
    source_population_df = pd.DataFrame(
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

    for suffix in ("AA", "AB"):
        for index in range(4, 16):
            source_population_df[f"C9D{suffix}{index:03d}"] = "0"
        for index in range(3, 5):
            source_population_df[f"C9G{suffix}{index:03d}"] = "0"

    population_df = parse_nhgis_1980_population(
        source_population_df, tmp_path / "nhgis_1980_block_groups.csv"
    )

    assert population_df.loc[0, "WHITE"] == 27
    assert population_df.loc[0, "BLACK"] == 9
    assert population_df.loc[0, "TOTPOP"] == 43


def test_2000_population_reader_preserves_integer_and_decimal_tracts(tmp_path):
    source_population_df = pd.DataFrame(
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

    population_df = parse_census_population(
        source_population_df,
        tmp_path / "census_2000_block_groups.csv",
        2000,
        "block_groups",
    )

    assert population_df["JOIN_KEY"].tolist() == ["060530001041", "060530104001"]
    assert not population_df["JOIN_KEY"].duplicated().any()


def test_nhgis_geography_requires_year_level_directory(tmp_path):
    old_directory = tmp_path / "ipums_geography_extracts" / "1990"
    old_directory.mkdir(parents=True)
    (old_directory / "old_shape.zip").touch()

    with pytest.raises(FileNotFoundError, match="1990/block_groups"):
        load_nhgis_geography(1990, tmp_path, "block_groups")


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

    geography_gdf = gpd.GeoDataFrame(
        {"GISJOIN": ["G010001000101"], "NHGISST": ["01"], "NHGISCTY": ["001"]},
        geometry=[Point(0, 0)],
        crs="EPSG:4326",
    )
    shape_dir.mkdir()
    shp_path = shape_dir / "US_blck_grp_1990.shp"
    geography_gdf.to_file(shp_path)

    import zipfile

    with zipfile.ZipFile(inner_zip, "w") as zf:
        for path in shape_dir.iterdir():
            zf.write(path, arcname=path.name)

    with zipfile.ZipFile(outer_zip, "w") as zf:
        zf.write(inner_zip, arcname=f"nhgis0046_shape/{inner_zip.name}")

    geography_result_gdf = read_nested_nhgis_shapefile(outer_zip, 1990, "block_groups")

    assert geography_result_gdf is not None
    assert geography_result_gdf["GISJOIN"].tolist() == ["G010001000101"]


def test_state_county_series_reads_fipsstco():
    geography_gdf = gpd.GeoDataFrame({"FIPSSTCO": ["02013"]}, geometry=[Point(0, 0)])

    state, county = state_county_series(geography_gdf)

    assert state.tolist() == ["02"]
    assert county.tolist() == ["013"]


def test_mixed_1980_layers_preserve_bna_state_and_county(tmp_path):
    import zipfile

    extract = tmp_path / "ipums_geography_extracts/1980/tracts"
    extract.mkdir(parents=True)
    for name, identifiers in [
        ("tract", {"NHGISST": ["010"], "NHGISCTY": ["0010"]}),
        ("bna", {"STATE80": ["02"], "COUNTY80": ["013"]}),
    ]:
        frame = gpd.GeoDataFrame(
            {"GISJOIN": [f"G{name}"], **identifiers},
            geometry=[Point(0, 0)], crs="EPSG:4326",
        )
        frame.to_file(tmp_path / f"US_{name}_1980.shp")
    with zipfile.ZipFile(extract / "mixed_shape.zip", "w") as archive:
        for path in tmp_path.glob("US_*"):
            archive.write(path, path.name)

    result = load_nhgis_geography(1980, tmp_path, "tracts").set_index("GISJOIN")
    assert result.loc["Gbna", "STATEFP"] == "02"
    assert result.loc["Gbna", "COUNTYFP"] == "013"
    assert result.loc["Gtract", "STATEFP"] == "01"


def test_place_keys_do_not_create_county_codes():
    geography_gdf = gpd.GeoDataFrame(
        {"STATEFP": ["06"], "PLACEFP": ["12345"]}, geometry=[Point(0, 0)]
    )
    population_df = pd.DataFrame(
        {
            "state": ["06"],
            "place": ["12345"],
            "NH_WHITE": ["10"],
            "NH_BLACK": ["5"],
            "TOTPOP": ["20"],
        }
    )

    standardized_geography_gdf = standardize_census_geography(geography_gdf, "places")
    parsed_population_df = parse_census_population(
        population_df, Path("places.csv"), 2020, "places"
    )

    assert (
        standardized_geography_gdf["JOIN_KEY"].tolist()
        == parsed_population_df["JOIN_KEY"].tolist()
        == ["0612345"]
    )
    assert "COUNTYFP" not in standardized_geography_gdf.columns
    assert "COUNTYFP" not in parsed_population_df.columns
    assert "JOIN_KEY" not in geography_gdf.columns


def test_2000_identifiers_agree_across_download_and_source_adapters():
    from capy_core.download.download_population_tables import geoid

    population_df = pd.DataFrame(
        {
            "state": ["06", "06"],
            "county": ["053", "053"],
            "tract": ["000104", "0104"],
            "block group": ["1", "1"],
            "NH_WHITE": ["10", "10"],
            "NH_BLACK": ["5", "5"],
            "TOTPOP": ["20", "20"],
        }
    )
    geography_gdf = gpd.GeoDataFrame(
        {
            "STATEFP00": ["06", "06"],
            "COUNTYFP00": ["053", "053"],
            "TRACTCE00": ["000104", "010400"],
            "BLKGRPCE00": ["1", "1"],
        },
        geometry=[Point(0, 0), Point(1, 1)],
    )

    parsed_population_df = parse_census_population(
        population_df, Path("2000.csv"), 2000, "block_groups"
    )
    standardized_geography_gdf = standardize_census_geography(
        geography_gdf, "block_groups"
    )
    downloaded_keys = geoid(
        population_df, ("state", "county", "tract", "block group"), 2000
    )

    assert (
        parsed_population_df["JOIN_KEY"].tolist()
        == standardized_geography_gdf["JOIN_KEY"].tolist()
        == downloaded_keys.tolist()
    )
    assert downloaded_keys.tolist() == ["060530001041", "060530104001"]
    geography_gdf.loc[0, "TRACTCE00"] = None
    with pytest.raises(ValueError, match="Missing Census tract"):
        standardize_census_geography(geography_gdf, "block_groups")
    population_df.loc[0, "tract"] = None
    with pytest.raises(ValueError, match="Missing Census tract"):
        parse_census_population(population_df, Path("2000.csv"), 2000, "block_groups")


def test_population_join_counts_losses_and_preserves_existing_1990_exception(capsys):
    from capy_core.preprocessing.build_census_geographies import join_population

    geography_gdf = gpd.GeoDataFrame(
        {"JOIN_KEY": ["a", "b", "c", "d", "e"], "STATEFP": ["01"] * 4 + ["02"]},
        geometry=[Point(index, 0) for index in range(5)],
    )
    population_df = pd.DataFrame(
        {
            "JOIN_KEY": ["a", "b", "c"],
            "STATEFP": ["01"] * 3,
            "WHITE": [10] * 3,
            "BLACK": [5] * 3,
            "TOTPOP": [20] * 3,
            "POC": [10] * 3,
        }
    )

    joined = join_population(geography_gdf, population_df, 2020, "tracts")

    assert joined.populated_geography_gdf["JOIN_KEY"].tolist() == ["a", "b", "c"]
    assert (
        joined.selected_count,
        joined.unmatched_count,
        joined.excluded_state_count,
    ) == (4, 1, 1)
    with pytest.raises(ValueError, match="more than 30%"):
        join_population(geography_gdf, population_df.iloc[:2], 2020, "tracts")
    permitted = join_population(geography_gdf, population_df.iloc[:2], 1990, "blocks")
    assert permitted.unmatched_count == 2
    assert len(permitted.populated_geography_gdf) == 2
    assert capsys.readouterr().out == ""


def test_population_join_rejects_duplicate_keys_and_missing_counts():
    from capy_core.preprocessing.build_census_geographies import join_population

    geography_gdf = gpd.GeoDataFrame(
        {"JOIN_KEY": ["a"], "STATEFP": ["01"]}, geometry=[Point(0, 0)]
    )
    population_df = pd.DataFrame(
        {
            "JOIN_KEY": ["a"],
            "STATEFP": ["01"],
            "WHITE": [10],
            "BLACK": [5],
            "TOTPOP": [20],
            "POC": [10],
        }
    )
    with pytest.raises(pd.errors.MergeError):
        join_population(
            geography_gdf, pd.concat([population_df, population_df]), 2020, "tracts"
        )
    with pytest.raises(pd.errors.MergeError):
        join_population(
            pd.concat([geography_gdf, geography_gdf]), population_df, 2020, "tracts"
        )
    geography_gdf.loc[0, "JOIN_KEY"] = None
    with pytest.raises(ValueError, match="missing join keys"):
        join_population(geography_gdf, population_df, 2020, "tracts")
    geography_gdf.loc[0, "JOIN_KEY"] = "a"
    population_df.loc[0, "TOTPOP"] = None
    with pytest.raises(ValueError, match="population counts"):
        join_population(geography_gdf, population_df, 2020, "tracts")


def test_configured_builder_writes_nodes_and_definition_prerequisites(
    tmp_path, monkeypatch
):
    import os
    import subprocess
    import sys

    import yaml

    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (tmp_path / "membership.csv").touch()
    config_path = config_dir / "run.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "repo_root": "..",
                "data_root": "inputs",
                "study_area_type": "max_city",
                "study_area_source": "membership.csv",
                "study_area_label": "example",
                "study_area_vintage": 2020,
                "census_geography_type": "tracts",
                "census_geography_years": [2010, 2020],
            }
        )
    )
    population_dir = tmp_path / "inputs" / "raw" / "population"
    geographies_dir = tmp_path / "inputs" / "raw" / "geographies"
    population_dir.mkdir(parents=True)
    requests = [
        (2010, "tracts"),
        (2020, "tracts"),
        (2020, "counties"),
        (2020, "places"),
    ]
    for year, level in requests:
        states = ["01", "02"] if level == "counties" else ["01"]
        keys = {"state": states}
        shape_keys = {"STATEFP": states}
        if level != "places":
            keys["county"] = ["001"] * len(states)
            shape_keys["COUNTYFP"] = keys["county"]
        if level == "tracts":
            keys["tract"] = ["000100"]
            shape_keys["TRACTCE"] = keys["tract"]
        if level == "places":
            keys["place"] = ["12345"]
            shape_keys["PLACEFP"] = keys["place"]

        population_df = pd.DataFrame(keys).assign(TOTPOP=20, NH_WHITE=10, NH_BLACK=5)
        population_df.to_csv(population_dir / f"census_{year}_{level}.csv", index=False)
        shape_dir = geographies_dir / f"census_{year}_{level}"
        shape_dir.mkdir(parents=True)
        geography_gdf = gpd.GeoDataFrame(
            shape_keys,
            geometry=[Point(-87, 32 + index) for index in range(len(states))],
            crs="EPSG:4326",
        )
        geography_gdf.to_file(shape_dir / "boundaries.shp")

    monkeypatch.chdir(config_dir)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "capy_core.preprocessing.build_census_geographies",
            "--config",
            str(config_path),
        ],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])},
        capture_output=True,
        text=True,
        check=True,
    )

    output_dir = tmp_path / "inputs" / "processed" / "census_geographies"
    paths = sorted(output_dir.rglob("*.gpkg"))
    assert len(paths) == 5
    for path in paths:
        populated_geography_gdf = gpd.read_file(path)
        assert populated_geography_gdf[
            ["WHITE", "BLACK", "TOTPOP", "POC"]
        ].values.tolist() == [[10, 5, 20, 10]]
        assert populated_geography_gdf.crs.to_string().lower() == "esri:102003"
    assert [
        line for line in result.stdout.splitlines() if line.startswith("Creating")
    ] == [
        f"Creating {year} {level} geography geopackage files"
        for year, level in requests
    ]
    assert "0 unmatched" in result.stdout
    assert (
        "has no" not in result.stdout
    )  # County-only states do not affect tract summaries.


def test_missing_inputs_report_both_download_commands(tmp_path):
    from capy_core.preprocessing.build_census_geographies import check_source_inputs

    with pytest.raises(FileNotFoundError) as error:
        check_source_inputs(
            1990, "tracts", tmp_path / "population", tmp_path / "geographies"
        )

    message = str(error.value)
    assert "download_population_tables --level tracts --year 1990" in message
    assert "download_geographies --level tracts --year 1990" in message
    assert 'ipums_geography_extracts"' in message


def test_tiger_tract_components_keep_fixed_width_interpretation():
    geography_gdf = gpd.GeoDataFrame(
        {
            "STATEFP00": ["06", "06"],
            "COUNTYFP00": ["053", "053"],
            "TRACTCE00": ["0104", "010400"],
        },
        geometry=[Point(0, 0), Point(1, 1)],
    )

    standardized_gdf = standardize_census_geography(geography_gdf, "tracts")

    assert standardized_gdf["JOIN_KEY"].tolist() == ["06053000104", "06053010400"]
    assert "JOIN_KEY" not in geography_gdf.columns
