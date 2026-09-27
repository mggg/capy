"""Population-based metro selection, whole-unit membership, and failed/empty rerun behavior."""

from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd
import pytest
from capy_core.assign_study_areas.assign_units import assign_units_by_representative_point
from capy_core.assign_study_areas.build_definitions import (
    build_city_candidates,
    build_metro_boundaries,
    build_study_area_definitions,
    rank_and_select_city_candidates,
)
from capy_core.assign_study_areas.count_city_populations import (
    assign_block_populations_to_places,
    read_2020_block_internal_points,
)
from capy_core.assign_study_areas.run_assignment import assign_study_areas
from capy_core.derived_file_paths import build_join_output_paths, build_population_output_path
from capy_core.geography_types import GeographyLevel, StudyAreaType
from capy_core.pipeline_config import PipelineConfig
from shapely.geometry import Point, box


@pytest.fixture
def counties_df():
    return gpd.GeoDataFrame(
        {
            "county_code": ["10001", "10003"],
            "GEOID": ["10001", "10003"],
            "state": ["10", "10"],
            "county": ["001", "003"],
            "NAME": ["West", "East"],
            "TOTPOP": [100, 200],
            "WHITE": [60, 120],
            "BLACK": [20, 40],
            "POC": [40, 80],
            "geometry": [box(0, 0, 10, 10), box(10, 0, 30, 10)],
        },
        crs="ESRI:102003",
    )


def test_city_ranking_counts_people_inside_metro_and_preserves_full_city(counties_df):
    roster_df = pd.DataFrame(
        {"metro_code": ["12345"], "metro_name": ["West metro"], "county_code": ["10001"]}
    )
    metros_df = build_metro_boundaries(counties_df, roster_df)
    places_df = gpd.GeoDataFrame(
        {
            "GEOID": ["1000001", "1000002", "1000003"],
            "state": ["10"] * 3,
            "NAME": ["Large across border", "Local city", "Boundary contact"],
            "TOTPOP": [1000, 50, 2000],
            "geometry": [box(8, 0, 20, 4), box(1, 1, 4, 4), box(10, 5, 20, 8)],
        },
        crs=counties_df.crs,
    )
    points_df = gpd.GeoDataFrame(
        {
            "block_code": ["a", "b", "c"],
            "county_code": ["10001", "10003", "10001"],
            "block_population": [5, 995, 50],
            "geometry": [Point(9, 2), Point(12, 2), Point(2, 2)],
        },
        crs=counties_df.crs,
    )
    before_df = places_df.copy()
    candidates_df = build_city_candidates(places_df, metros_df)
    city_counties_df = assign_block_populations_to_places(points_df, places_df)
    scores_df = rank_and_select_city_candidates(candidates_df, city_counties_df, roster_df)
    definitions_df, _ = build_study_area_definitions(
        counties_df, StudyAreaType.MAX_CITY, 2020, metros_df, places_df, scores_df
    )

    assert scores_df.set_index("place_code").population_inside_metro.to_dict() == {
        "1000001": 5,
        "1000002": 50,
    }
    assert definitions_df.selected_place_code.tolist() == ["1000002"]
    assert definitions_df.county_codes.tolist() == [["10001"]]
    assert definitions_df.metro_county_codes.tolist() == [["10001"]]
    assert definitions_df.geometry.iloc[0].equals(places_df.geometry.iloc[1])
    pd.testing.assert_frame_equal(places_df, before_df)

    # A different block distribution can select the cross-border city; its full boundary remains.
    city_counties_df.loc[
        city_counties_df.place_code.eq("1000001") & city_counties_df.county_code.eq("10001"),
        "block_population",
    ] = 500
    city_counties_df.loc[
        city_counties_df.place_code.eq("1000001") & city_counties_df.county_code.eq("10003"),
        "block_population",
    ] = 500
    scores_df = rank_and_select_city_candidates(candidates_df, city_counties_df, roster_df)
    definitions_df, _ = build_study_area_definitions(
        counties_df, StudyAreaType.MAX_CITY, 2020, metros_df, places_df, scores_df
    )
    assert definitions_df.county_codes.tolist() == [["10001", "10003"]]
    assert definitions_df.metro_county_codes.tolist() == [["10001"]]
    assert definitions_df.geometry.iloc[0].equals(places_df.geometry.iloc[0])


def test_complete_metro_and_maximum_county_selection(counties_df):
    roster_df = pd.DataFrame(
        {
            "metro_code": ["12345", "12345"],
            "metro_name": ["Metro", "Metro"],
            "county_code": ["10001", "10003"],
        }
    )

    with pytest.raises(ValueError, match="missing.*10003"):
        build_metro_boundaries(counties_df.iloc[:1], roster_df)

    metros_df = build_metro_boundaries(counties_df, roster_df)
    definitions_df, candidates_df = build_study_area_definitions(
        counties_df, StudyAreaType.MAX_COUNTY, 2020, metros_df
    )
    assert definitions_df.selected_county_code.tolist() == ["10003"]
    assert candidates_df.loc[candidates_df.selected, "county_code"].tolist() == ["10003"]

    cbsa_df, _ = build_study_area_definitions(counties_df, StudyAreaType.CBSA, 2020, metros_df)
    assert cbsa_df.county_codes.tolist() == [["10001", "10003"]]
    assert cbsa_df.definition_population.tolist() == [300]
    assert cbsa_df.geometry.iloc[0].equals(box(0, 0, 30, 10))


def test_representative_point_membership_retains_zero_counts_and_boundary_points():
    units_df = gpd.GeoDataFrame(
        {
            "GEOID": ["zero", "crossing"],
            "TOTPOP": [0, 20],
            "WHITE": [0, 10],
            "BLACK": [0, 4],
            "POC": [0, 10],
            "geometry": [box(0, 0, 2, 2), box(1, 0, 3, 2)],
        },
        crs="ESRI:102003",
    )
    areas_df = gpd.GeoDataFrame(
        {"study_area_id": ["area"], "geometry": [box(0, 0, 2, 2)]}, crs=units_df.crs
    )
    memberships_df = assign_units_by_representative_point(units_df, areas_df)

    assert set(memberships_df.GEOID) == {"zero", "crossing"}
    assert memberships_df.TOTPOP.sum() == 20
    assert units_df.geometry.iloc[1].area == 4


def write_join_outputs(tmp_path, level, units_df):
    population_path = build_population_output_path(2020, level, "10")
    matched_path, population_exclusions_path, boundary_exclusions_path = build_join_output_paths(
        population_path
    )
    output_df = units_df.assign(CENSUS_YEAR=2020, GEOGRAPHY_LEVEL=level.value)
    matched_path = tmp_path / "joined" / matched_path
    matched_path.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_parquet(matched_path)
    pd.DataFrame({"GEOID": []}).to_parquet(tmp_path / "joined" / population_exclusions_path)
    gpd.GeoDataFrame({"GEOID": [], "geometry": []}, crs=units_df.crs).to_parquet(
        tmp_path / "joined" / boundary_exclusions_path
    )
    return matched_path


def test_county_workflow_records_empty_rerun_and_invalidates_failed_outputs(tmp_path, counties_df):
    config = PipelineConfig(
        census_geography_years=(2020,),
        census_geography_levels=("tracts",),
        study_area_type="county",
        joined_geography_directory=Path("joined"),
        study_area_directory=Path("areas"),
        file_path_patterns=(
            "census/2020/counties/10/*",
            "census/2020/tracts/10/*",
            "tiger/2020/counties/*",
            "tiger/2020/tracts/tl_2020_10_tract.zip",
        ),
    )
    county_path = write_join_outputs(tmp_path, GeographyLevel.COUNTY, counties_df)
    units_df = counties_df.iloc[:1].assign(GEOID="10001000100", geometry=[box(1, 1, 4, 4)])
    write_join_outputs(tmp_path, GeographyLevel.TRACT, units_df)
    summary_df = assign_study_areas(config, tmp_path).set_index("study_area_id")
    assert summary_df.status.to_dict() == {
        "county_10001": "ready",
        "county_10003": "no_units_selected",
    }
    assert summary_df.loc["county_10001", "TOTPOP"] == 100

    units_df.geometry = [box(40, 40, 41, 41)]
    write_join_outputs(tmp_path, GeographyLevel.TRACT, units_df)
    assert assign_study_areas(config, tmp_path).status.eq("no_units_selected").all()
    membership_path = (
        tmp_path / "areas/county/2020/memberships/2020/tracts/DE_2020_memberships.parquet"
    )
    assert pd.read_parquet(membership_path).empty

    county_path.unlink()
    with pytest.raises(FileNotFoundError):
        assign_study_areas(config, tmp_path)
    assert not (tmp_path / "areas/county/2020/summary.parquet").exists()
    assert not membership_path.exists()


def test_tiger_internal_points_require_exact_block_population_agreement(tmp_path):
    source_df = gpd.GeoDataFrame(
        {
            "GEOID20": ["100010001001001"],
            "COUNTYFP20": ["001"],
            "POP20": [7],
            "INTPTLAT20": ["39.0"],
            "INTPTLON20": ["-75.0"],
            "geometry": [box(-76, 38, -74, 40)],
        },
        crs="EPSG:4269",
    )
    source_df.to_file(tmp_path / "blocks.shp")
    archive_path = tmp_path / "blocks.zip"

    with ZipFile(archive_path, "w") as archive:
        for component_path in tmp_path.glob("blocks.*"):
            if component_path.suffix != ".zip":
                archive.write(component_path, component_path.name)

    population_df = pd.DataFrame({"GEOID": ["100010001001001"], "TOTPOP": [7]})
    points_df = read_2020_block_internal_points(archive_path, population_df)
    assert points_df.geometry.iloc[0].equals(Point(-75, 39))

    population_df.loc[0, "TOTPOP"] = 8
    with pytest.raises(ValueError, match="populations disagree"):
        read_2020_block_internal_points(archive_path, population_df)


def test_tied_city_scores_are_stable_under_input_order():
    candidates_df = pd.DataFrame(
        {
            "metro_code": ["12345", "12345"],
            "place_code": ["1000002", "1000001"],
            "city_population": [10, 10],
        }
    )
    counts_df = pd.DataFrame(
        {
            "county_code": ["10001", "10001"],
            "place_code": ["1000002", "1000001"],
            "block_population": [10, 10],
        }
    )
    roster_df = pd.DataFrame({"county_code": ["10001"], "metro_code": ["12345"]})
    scores_df = rank_and_select_city_candidates(candidates_df, counts_df, roster_df)
    reversed_df = rank_and_select_city_candidates(
        candidates_df.iloc[::-1], counts_df.iloc[::-1], roster_df
    )

    pd.testing.assert_frame_equal(scores_df, reversed_df)
    assert scores_df.loc[scores_df.selected, "place_code"].tolist() == ["1000001"]
    assert scores_df.selection_reason.eq("equal_population_smallest_place_code_wins").all()


def test_missing_supported_states_fail_but_historical_puerto_rico_is_unavailable():
    from capy_core.assign_study_areas.assign_units import (
        check_node_state_coverage,
        summarize_memberships,
    )
    from capy_core.join_geographies.select_inputs import GeographyJoinInputs

    definitions_df = gpd.GeoDataFrame(
        {
            "study_area_id": ["county_10001", "county_72001"],
            "county_codes": [["10001"], ["72001"]],
            "geometry": [box(0, 0, 1, 1), box(3, 0, 4, 1)],
        },
        crs="ESRI:102003",
    )
    selection = GeographyJoinInputs(
        1980, GeographyLevel.TRACT, {}, {"10": Path("population.parquet")}
    )
    unavailable = check_node_state_coverage(definitions_df, selection)
    state_summary_df = pd.DataFrame(
        {
            "study_area_id": ["county_10001"],
            "unit_count": [1],
            "TOTPOP": [5],
            "WHITE": [3],
            "BLACK": [1],
            "POC": [2],
        }
    )
    summary_df = summarize_memberships(
        definitions_df, [state_summary_df], selection, unavailable
    ).set_index("study_area_id")

    assert summary_df.loc["county_72001", "status"] == "historical_coverage_unavailable"
    assert pd.isna(summary_df.loc["county_72001", "TOTPOP"])

    selection = GeographyJoinInputs(
        2020, GeographyLevel.TRACT, {}, {"10": Path("population.parquet")}
    )
    with pytest.raises(ValueError, match="missing 2020.*72"):
        check_node_state_coverage(definitions_df, selection)


@pytest.mark.parametrize(
    "node_levels,expected_levels",
    [(("tracts",), ["tracts"]), (("tracts", "blocks"), ["tracts", "blocks"])],
)
def test_geography_join_skips_ranking_only_block_polygons(
    tmp_path, monkeypatch, node_levels, expected_levels
):
    from capy_core.join_geographies import join_tables
    from capy_core.join_geographies.select_inputs import GeographyJoinInputs

    selections = [
        GeographyJoinInputs(2020, level, {}, {})
        for level in (GeographyLevel.TRACT, GeographyLevel.BLOCK)
    ]
    joined_levels = []

    def record_join(selection, *directories):
        joined_levels.append(selection.geography_level.value)
        return [pd.DataFrame({"census_year": [2020]})], [pd.DataFrame({"GEOID": []})]

    monkeypatch.setattr(join_tables, "select_geography_join_inputs", lambda config: selections)
    monkeypatch.setattr(join_tables, "join_selected_geography", record_join)
    config = PipelineConfig(census_geography_years=(2020,), census_geography_levels=node_levels)
    join_tables.join_geography_tables(config, tmp_path)

    assert joined_levels == expected_levels


def test_filename_filters_cannot_silently_remove_a_configured_node_year(tmp_path):
    config = PipelineConfig(
        census_geography_years=(1990, 2020),
        census_geography_levels=("tracts",),
        study_area_type="county",
        file_path_patterns=(
            "census/2020/counties/10/*",
            "census/2020/tracts/10/*",
            "tiger/2020/counties/*",
            "tiger/2020/tracts/tl_2020_10_tract.zip",
        ),
    )

    with pytest.raises(ValueError, match="filters omit configured node selections.*1990"):
        assign_study_areas(config, tmp_path)
