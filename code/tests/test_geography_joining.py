"""Population conservation, geometry repair, unresolved identities, and configured join outputs."""

from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd
import pytest
from national_pipeline.geography_types import GeographyLevel, StudyAreaType
from national_pipeline.join_geographies.join_population import (
    ExclusionReason,
    check_population_join_input,
    classify_1990_zero_population_blocks,
    join_population_to_boundaries,
    merge_1980_parent_geometries,
    repair_and_project_boundaries,
)
from national_pipeline.join_geographies.join_tables import join_geography_tables
from national_pipeline.join_geographies.repair_1980_sources import PARENT_GEOMETRY_MERGES_1980
from national_pipeline.join_geographies.select_inputs import (
    GeographyJoinInputs,
    select_geography_join_inputs,
)
from national_pipeline.pipeline_config import PipelineConfig
from shapely.geometry import Polygon, box


def build_population_table(geographic_ids, populations, year=2020, level="tracts"):
    """Build a Delaware population table with source metadata and all residents in WHITE."""
    return pd.DataFrame(
        {
            "GEOID": geographic_ids,
            "state": ["10"] * len(geographic_ids),
            "TOTPOP": populations,
            "WHITE": populations,
            "BLACK": [0] * len(geographic_ids),
            "POC": [0] * len(geographic_ids),
            "CENSUS_YEAR": year,
            "CENSUS_DATASET": "pl",
            "GEOGRAPHY_LEVEL": level,
            "SOURCE_FILE": "source.json",
            "SOURCE_ROW": range(1, len(geographic_ids) + 1),
        }
    )


def build_boundary_table(geographic_ids, geometries=None):
    """Build Delaware boundaries, using adjacent unit squares unless geometry is supplied."""
    return gpd.GeoDataFrame(
        {
            "GEOID": geographic_ids,
            "state": ["10"] * len(geographic_ids),
            "county": "001",
            "BOUNDARY_SOURCE_FILE": "boundaries.zip",
            "BOUNDARY_SOURCE_MEMBER": "boundaries.shp",
            "BOUNDARY_SOURCE_ID": geographic_ids,
            "BOUNDARY_WATER_BLOCK": False,
        },
        geometry=geometries
        or [box(index, 0, index + 1, 1) for index in range(len(geographic_ids))],
        crs="ESRI:102003",
    )


def test_join_preserves_zero_records_and_never_invents_population_for_unmatched_polygons(tmp_path):
    boundaries_df, _ = repair_and_project_boundaries(
        build_boundary_table(["10001000100", "10001000200", "10001000300"])
    )
    population_df = build_population_table(
        ["10001000100", "10001000200", "10001000400"], [25, 0, 7]
    )

    result = join_population_to_boundaries(boundaries_df, population_df, 2020, GeographyLevel.TRACT)

    selection = GeographyJoinInputs(2020, GeographyLevel.TRACT, {}, {})
    assert (
        classify_1990_zero_population_blocks(result, selection, "10", tmp_path / "absent") is result
    )

    assert result.matched_geography_df.TOTPOP.tolist() == [25, 0]
    assert result.unmatched_population_df.TOTPOP.tolist() == [7]
    assert result.unmatched_boundaries_df.GEOID.tolist() == ["10001000300"]
    assert result.unmatched_boundaries_df.KNOWN_TOTAL_POPULATION.isna().all()
    assert "TOTPOP" not in result.unmatched_boundaries_df
    assert (
        result.matched_geography_df.TOTPOP.sum() + result.unmatched_population_df.TOTPOP.sum() == 32
    )


def test_invalid_geometry_is_repaired_and_all_four_parent_merges_preserve_source_accounting():
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)])
    repaired_boundaries_df, repairs_df = repair_and_project_boundaries(
        build_boundary_table(["10001000100"], [bowtie])
    )

    assert repaired_boundaries_df.is_valid.all()
    assert repaired_boundaries_df.GEOID.tolist() == ["10001000100"]
    assert repairs_df.area_before_m2.tolist() == [0]
    assert repairs_df.area_after_m2.tolist() == [1]

    geographic_ids = [
        identifier for pair in PARENT_GEOMETRY_MERGES_1980.items() for identifier in pair
    ]
    boundaries_df, _ = repair_and_project_boundaries(build_boundary_table(geographic_ids))
    boundaries_df["BOUNDARY_PART_COUNT"] = 1
    boundaries_df["MERGED_BOUNDARY_SOURCES"] = ""
    merged_boundaries_df = merge_1980_parent_geometries(boundaries_df)
    merged_boundaries_df, _ = repair_and_project_boundaries(merged_boundaries_df)

    assert set(merged_boundaries_df.GEOID) == set(PARENT_GEOMETRY_MERGES_1980.values())
    assert merged_boundaries_df.BOUNDARY_PART_COUNT.tolist() == [2] * 4
    assert merged_boundaries_df.area.tolist() == [2] * 4
    assert merged_boundaries_df.MERGED_BOUNDARY_SOURCES.ne("").all()


def test_water_and_untracted_exclusions_require_their_documented_source_rules():
    boundaries_df, _ = repair_and_project_boundaries(
        build_boundary_table(["G10000100000199", "G1000010nodata"])
    )
    boundaries_df.loc[0, "BOUNDARY_WATER_BLOCK"] = True
    population_df = build_population_table(["G1000010123499", "G1000010999999"], [3, 5], 1980)

    result = join_population_to_boundaries(boundaries_df, population_df, 1980, GeographyLevel.TRACT)

    assert result.unmatched_population_df.EXCLUSION_REASON.tolist() == [
        ExclusionReason.SHIP_CREW,
        ExclusionReason.UNTRACTED_REMAINDER_1980,
    ]
    assert result.unmatched_boundaries_df.KNOWN_TOTAL_POPULATION.iloc[0] == 0
    assert pd.isna(result.unmatched_boundaries_df.KNOWN_TOTAL_POPULATION.iloc[1])


def test_configured_join_roundtrip_and_failed_rerun_remove_only_selected_outputs(tmp_path):
    config = PipelineConfig(
        census_geography_years=(2020,),
        census_geography_levels=(GeographyLevel.TRACT,),
        study_area_type=StudyAreaType.COUNTY,
        raw_data_directory=tmp_path / "raw",
        processed_population_directory=tmp_path / "population",
        joined_geography_directory=tmp_path / "geography",
        file_path_patterns=(
            "census/2020/tracts/10/state.json",
            "tiger/2020/tracts/tl_2020_10_tract.zip",
        ),
    )

    source_shapes_directory = tmp_path / "shapes"
    source_shapes_directory.mkdir()

    gpd.GeoDataFrame(
        {
            "GEOID": ["10001000100", "10001000200"],
            "STATEFP": ["10", "10"],
            "COUNTYFP": ["001", "001"],
            "TRACTCE": ["000100", "000200"],
        },
        geometry=[box(-75, 39, -74.9, 39.1), box(-75, 39.1, -74.9, 39.2)],
        crs="EPSG:4269",
    ).to_file(source_shapes_directory / "tracts.shp")

    archive_path = config.raw_data_directory / "tiger/2020/tracts/tl_2020_10_tract.zip"
    archive_path.parent.mkdir(parents=True)

    with ZipFile(archive_path, "w") as archive:
        for shape_file_path in source_shapes_directory.iterdir():
            archive.write(shape_file_path, shape_file_path.name)

    population_path = (
        config.processed_population_directory / "2020/tracts/DE_2020_populations.parquet"
    )
    population_path.parent.mkdir(parents=True)
    population_df = build_population_table(
        ["10001000100", "10001000200", "10001000300"], [25, 0, 7]
    )
    population_df.to_parquet(population_path)
    original_population_bytes = population_path.read_bytes()

    summary_df = join_geography_tables(config, tmp_path)

    geography_output_path = (
        config.joined_geography_directory / "2020/tracts/DE_2020_geography.parquet"
    )
    saved_geography_df = gpd.read_parquet(geography_output_path)

    repair_report_df = pd.read_csv(config.joined_geography_directory / "geometry_repairs.csv")
    assert "BOUNDARY_PART_COUNT" not in repair_report_df
    assert "MERGED_BOUNDARY_SOURCES" not in repair_report_df
    assert saved_geography_df.BOUNDARY_PART_COUNT.tolist() == [1, 1]
    assert saved_geography_df.MERGED_BOUNDARY_SOURCES.tolist() == ["", ""]
    assert saved_geography_df.TOTPOP.tolist() == [25, 0]
    assert saved_geography_df.crs.to_authority() == ("ESRI", "102003")
    expected_summary_df = pd.DataFrame(
        {
            "census_year": 2020,
            "geography_level": "tracts",
            "state_code": "10",
            "population_group": ["TOTPOP", "WHITE", "BLACK", "POC"],
            "input_population": [32, 32, 0, 0],
            "matched_population": [25, 25, 0, 0],
            "unmatched_population": [7, 7, 0, 0],
        }
    )
    pd.testing.assert_frame_equal(summary_df, expected_summary_df)
    saved_summary_df = pd.read_csv(
        config.joined_geography_directory / "join_summary.csv", dtype={"state_code": str}
    )
    pd.testing.assert_frame_equal(saved_summary_df, expected_summary_df)
    assert population_path.read_bytes() == original_population_bytes

    unselected_output_path = geography_output_path.with_name("AK_2020_geography.parquet")
    unselected_output_path.write_bytes(b"unselected output")
    population_df["CENSUS_YEAR"] = 2010
    population_df.to_parquet(population_path)

    with pytest.raises(ValueError, match="CENSUS_YEAR disagrees"):
        join_geography_tables(config, tmp_path)

    assert not geography_output_path.exists()
    assert not (config.joined_geography_directory / "join_summary.csv").exists()
    assert unselected_output_path.read_bytes() == b"unselected output"


@pytest.mark.parametrize("failure", ["duplicate", "county", "empty_geometry"])
def test_join_rejects_ambiguous_identity_and_unusable_geometry(failure):
    boundaries_df = build_boundary_table(["10001000100", "10001000200"])
    population_df = build_population_table(["10001000100", "10001000200"], [1, 2])

    if failure == "duplicate":
        population_df.loc[1, "GEOID"] = "10001000100"
    elif failure == "county":
        population_df["county"] = "003"
    else:
        boundaries_df.loc[0, "geometry"] = Polygon()

    with pytest.raises(ValueError):
        boundaries_df, _ = repair_and_project_boundaries(boundaries_df)
        join_population_to_boundaries(boundaries_df, population_df, 2020, GeographyLevel.TRACT)


def test_historical_population_county_must_agree_with_its_join_identity():
    population_df = build_population_table(["G10000100401"], [5], 1980)
    population_df["GISJOIN"] = population_df.GEOID
    population_df["STATEA"] = "10"
    population_df["COUNTYA"] = "003"

    with pytest.raises(ValueError, match="COUNTYA disagrees"):
        check_population_join_input(population_df, 1980, GeographyLevel.TRACT, "10")


def test_swapped_state_archives_are_rejected_before_population_matching(tmp_path, monkeypatch):
    config = PipelineConfig(
        census_geography_years=(2020,),
        census_geography_levels=(GeographyLevel.TRACT,),
        study_area_type=StudyAreaType.COUNTY,
        raw_data_directory=tmp_path / "raw",
        processed_population_directory=tmp_path / "population",
        joined_geography_directory=tmp_path / "geography",
        file_path_patterns=(
            "census/2020/tracts/10/state.json",
            "census/2020/tracts/24/state.json",
            "tiger/2020/tracts/tl_2020_10_tract.zip",
            "tiger/2020/tracts/tl_2020_24_tract.zip",
        ),
    )

    from national_pipeline.join_geographies import select_inputs
    from national_pipeline.retrieve_data.prepare_file_requests import select_raw_file_requests

    selected_requests = select_raw_file_requests(config)
    monkeypatch.setattr(
        select_inputs, "select_raw_file_requests", lambda config: list(reversed(selected_requests))
    )
    (selection,) = select_geography_join_inputs(config)
    assert selection.boundary_paths_by_state == {
        "10": "tiger/2020/tracts/tl_2020_10_tract.zip",
        "24": "tiger/2020/tracts/tl_2020_24_tract.zip",
    }
    monkeypatch.setattr(select_inputs, "select_raw_file_requests", select_raw_file_requests)

    def read_swapped_archive(archive_path, *args):
        state_code = "24" if "_10_" in archive_path.name else "10"
        boundaries_df = build_boundary_table([f"{state_code}001000100"])
        boundaries_df["state"] = state_code
        yield boundaries_df

    monkeypatch.setattr(
        "national_pipeline.join_geographies.join_tables.read_boundary_archive", read_swapped_archive
    )

    with pytest.raises(ValueError, match="Boundary contents disagree with state 10"):
        join_geography_tables(config, tmp_path)

    config.file_path_patterns = config.file_path_patterns[:-1]

    with pytest.raises(ValueError, match="matching population and boundary states"):
        join_geography_tables(config, tmp_path)


@pytest.mark.parametrize(
    ("source_state_codes", "failure_message"),
    [
        (("10", "10"), "More than one boundary table"),
        (("10",), "Selected population states lack selected boundaries"),
    ],
)
def test_state_coverage_checks_close_the_stream_without_rejoining_a_state(
    tmp_path, monkeypatch, source_state_codes, failure_message
):
    from national_pipeline.join_geographies import join_tables

    config = PipelineConfig(
        raw_data_directory=tmp_path / "raw",
        processed_population_directory=tmp_path / "population",
        joined_geography_directory=tmp_path / "geography",
    )
    selection = GeographyJoinInputs(
        census_year=2020,
        geography_level=GeographyLevel.COUNTY,
        boundary_paths_by_state={None: "counties.zip"},
        population_paths_by_state={
            "10": Path("2020/counties/DE_2020_populations.parquet"),
            "24": Path("2020/counties/MD_2020_populations.parquet"),
        },
    )
    population_path = (
        config.processed_population_directory / selection.population_paths_by_state["10"]
    )
    population_path.parent.mkdir(parents=True)
    build_population_table(["10001"], [25], level="counties").to_parquet(population_path)

    events = []
    save_state = join_tables.join_and_save_state

    def read_state_tables(*args):
        try:
            for state_code in source_state_codes:
                events.append(f"read {state_code}")
                yield build_boundary_table(["10001"])
        finally:
            events.append("closed")

    def record_state_join(boundaries_df, selection, state_code, *directories):
        events.append(f"join {state_code}")
        return save_state(boundaries_df, selection, state_code, *directories)

    monkeypatch.setattr(join_tables, "select_geography_join_inputs", lambda config: [selection])
    monkeypatch.setattr(join_tables, "read_boundary_archive", read_state_tables)
    monkeypatch.setattr(join_tables, "join_and_save_state", record_state_join)

    with pytest.raises(ValueError, match=failure_message):
        join_geography_tables(config, tmp_path)

    expected_events = ["read 10", "join 10"]
    if len(source_state_codes) == 2:
        expected_events.append("read 10")

    assert events == [*expected_events, "closed"]
    assert not (config.joined_geography_directory / "join_summary.csv").exists()
