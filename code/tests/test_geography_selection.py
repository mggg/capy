"""Run selections drive both population and boundary inputs, including study-area data."""

import pytest
from capy_core.geography_types import GeographyLevel
from capy_core.pipeline_config import (
    PipelineConfig,
    RawDataSubdirectories,
    load_configuration,
)
from capy_core.retrieve_data.census.build_published_file_requests import build_tiger_file_requests
from capy_core.retrieve_data.census.retrieve_tables import resolve_census_query_parameters
from capy_core.retrieve_data.prepare_file_requests import (
    build_geography_requests,
    build_raw_file_requests,
    filter_raw_file_requests,
)
from capy_core.retrieve_data.raw_file_requests import (
    CensusDataset,
    CensusFileRequest,
    GeographyRequest,
    NhgisTableFileRequest,
)
from capy_core.retrieve_data.retrieve_files import retrieve_raw_data


def test_invalid_geography_assignment_preserves_yaml_selection(tmp_path):
    path = tmp_path / "run.yaml"
    path.write_text("census_geography_levels: [block_groups]\nstudy_area_type: max_county\n")

    config = load_configuration(path)

    with pytest.raises(ValueError, match="Graph nodes"):
        config.census_geography_levels = (GeographyLevel.PLACE,)

    assert config.census_geography_levels == (GeographyLevel.BLOCK_GROUP,)


@pytest.mark.parametrize(
    "level,provider_name,parent",
    [
        (GeographyLevel.STATE, "state", None),
        (GeographyLevel.COUNTY, "county", "state:10"),
        (GeographyLevel.TRACT, "tract", "state:10 county:*"),
        (GeographyLevel.BLOCK_GROUP, "block group", "state:10 county:* tract:*"),
        (GeographyLevel.BLOCK, "block", "state:10 county:* tract:*"),
        (GeographyLevel.PLACE, "place", "state:10"),
    ],
)
def test_geography_enums_produce_census_api_names(tmp_path, level, provider_name, parent):
    request = CensusFileRequest(
        destination_relative_path="population.json",
        census_year=2020,
        dataset=CensusDataset.PL_94_171,
        variables="NAME",
        geography_level=level,
        state_code=None if level == GeographyLevel.STATE else "10",
    )
    expected = {"get": "NAME", "for": f"{provider_name}:*"}
    if parent is not None:
        expected["in"] = parent

    assert resolve_census_query_parameters(request, tmp_path, RawDataSubdirectories()) == expected


@pytest.mark.parametrize(
    "levels,years,area_type,vintage,expected",
    [
        (
            ["tracts"],
            [1990],
            "max_city",
            2020,
            {(1990, "tracts"), (2020, "counties"), (2020, "places")},
        ),
        (["blocks"], [1980, 2020], "county", 2020, {(2020, "blocks"), (2020, "counties")}),
        (["counties"], [2020, 2020], "county", 2020, {(2020, "counties")}),
        (["tracts"], [2020], "county", 1980, {(2020, "tracts"), (1980, "counties")}),
    ],
)
def test_shared_selection_adds_definition_inputs_and_omits_unsupported_pairs(
    levels, years, area_type, vintage, expected
):
    config = PipelineConfig(
        census_geography_levels=levels,
        census_geography_years=years,
        study_area_type=area_type,
        study_area_vintage=vintage,
    )
    requests = build_geography_requests(config)

    assert {(request.census_year, request.geography_level) for request in requests} == expected
    assert len(requests) == len(expected)


def test_modern_selection_matches_populations_and_boundaries():
    config = PipelineConfig(
        census_geography_levels=("tracts",),
        census_geography_years=(2010,),
        study_area_type="county",
        study_area_vintage=2020,
    )
    requests = build_raw_file_requests(config)
    population_pairs = {
        (request.census_year, request.geography_level)
        for request in requests
        if isinstance(request, CensusFileRequest)
    }
    destinations = [request.destination_relative_path for request in requests]
    boundary_pairs = {
        tuple(path.split("/")[1:3]) for path in destinations if path.startswith("tiger/")
    }

    assert population_pairs == {
        (2010, GeographyLevel.TRACT),
        (2020, GeographyLevel.COUNTY),
        (2010, GeographyLevel.STATE),
        (2020, GeographyLevel.STATE),
    }
    assert boundary_pairs == {("2010", "tracts"), ("2020", "counties")}
    assert not any(
        path.startswith(("nhgis/", "census_1980_stf1a/", "metro_membership_tables/"))
        for path in destinations
    )
    assert len(destinations) == len(set(destinations))
    with pytest.raises(ValueError, match="No defined files match"):
        filter_raw_file_requests(requests, ("tiger/2010/blocks/*",))


@pytest.mark.parametrize(
    "census_year,geography_level,expected_destination,expected_url_path,expected_count",
    [
        (
            2000,
            GeographyLevel.BLOCK_GROUP,
            "2000/block_groups/tl_2010_01_bg00.zip",
            "TIGER2010/BG/2000/tl_2010_01_bg00.zip",
            52,
        ),
        (
            2010,
            GeographyLevel.BLOCK,
            "2010/blocks/tl_2010_01_tabblock10.zip",
            "TIGER2010/TABBLOCK/2010/tl_2010_01_tabblock10.zip",
            52,
        ),
        (
            2020,
            GeographyLevel.BLOCK,
            "2020/blocks/tl_2020_01_tabblock20.zip",
            "TIGER2020/TABBLOCK20/tl_2020_01_tabblock20.zip",
            52,
        ),
        (
            2020,
            GeographyLevel.COUNTY,
            "2020/counties/tl_2020_us_county.zip",
            "TIGER2020/COUNTY/tl_2020_us_county.zip",
            1,
        ),
        (
            2020,
            GeographyLevel.PLACE,
            "2020/places/tl_2020_01_place.zip",
            "TIGER2020/PLACE/tl_2020_01_place.zip",
            52,
        ),
    ],
)
def test_tiger_requests_keep_vintage_names_and_geographic_coverage(
    census_year, geography_level, expected_destination, expected_url_path, expected_count
):
    selection = GeographyRequest(census_year=census_year, geography_level=geography_level)
    requests = build_tiger_file_requests(
        RawDataSubdirectories(census_boundary_files="custom/boundaries"),
        (selection, selection),
    )

    assert len(requests) == expected_count
    assert requests[0].destination_relative_path == f"custom/boundaries/{expected_destination}"
    assert requests[0].url == f"https://www2.census.gov/geo/tiger/{expected_url_path}"


def test_historical_selection_downloads_only_required_levels_with_stable_paths():
    config = PipelineConfig(census_geography_levels=("tracts",), census_geography_years=(1990,))
    requests = {
        request.destination_relative_path: request for request in build_raw_file_requests(config)
    }
    default_requests = {
        request.destination_relative_path: request
        for request in build_raw_file_requests(PipelineConfig())
    }

    assert (
        requests["nhgis/1990/tracts/population.zip"]
        == default_requests["nhgis/1990/tracts/population.zip"]
    )
    assert {path for path in requests if path.startswith("nhgis/")} == {
        "nhgis/1990/tracts/population.zip",
        "nhgis/1990/states/population.zip",
        "nhgis/1990/tracts/boundaries.zip",
    }
    assert "census/2020/counties/10/state.json" in requests
    assert "census/2020/places/10/state.json" in requests
    assert "tiger/2020/places/tl_2020_10_place.zip" in requests
    assert "tiger/2020/counties/tl_2020_us_county.zip" in requests
    assert "metro_membership_tables/list1_march_2020.xls" in requests
    assert "population_reference_tables/census_working_paper_56_1990_tableE-01.xlsx" in requests
    assert requests["nhgis/1990/tracts/population.zip"].geographic_levels == ("tract",)
    assert not any("tableA-" in path for path in requests)
    assert not any("1980" in path for path in requests)
    assert not any(path.startswith("census_1980_stf1a/") for path in requests)


def test_historical_definition_year_adds_its_population_and_reference_inputs():
    config = PipelineConfig(
        census_geography_levels=("tracts",),
        census_geography_years=(2020,),
        study_area_type="county",
        study_area_vintage=1980,
    )
    paths = {request.destination_relative_path for request in build_raw_file_requests(config)}

    assert {
        "nhgis/1980/counties/population.zip",
        "nhgis/1980/counties/boundaries.zip",
        "nhgis/1980/states/population.zip",
        "population_reference_tables/census_working_paper_56_1980_tableE-03.xlsx",
        "population_reference_tables/census_working_paper_56_1980_tableA-03.xlsx",
    } <= paths
    assert not any("/tracts/" in path and path.startswith("nhgis/") for path in paths)
    assert not any(path.startswith("census_1980_stf1a/") for path in paths)
    assert not any("1990" in path for path in paths)
    assert "metro_membership_tables/list1_march_2020.xls" not in paths


@pytest.mark.parametrize("year", [1980, 1990, 2000, 2010, 2020])
@pytest.mark.parametrize("level", ["counties", "tracts", "block_groups", "blocks"])
def test_each_supported_run_requests_only_selected_levels_and_required_support(year, level):
    if year == 1980 and level in ("block_groups", "blocks"):
        pytest.skip("No supported 1980 block or block-group boundaries")
    config = PipelineConfig(
        census_geography_levels=(level,),
        census_geography_years=(year,),
        study_area_type="county",
        study_area_vintage=year,
    )
    requests = build_raw_file_requests(config)
    paths = {request.destination_relative_path for request in requests}
    expected_levels = {level, "counties", "states"}
    if year in (1980, 1990):
        population_requests = [
            request
            for request in requests
            if isinstance(request, NhgisTableFileRequest)
            and request.destination_relative_path.endswith("/population.zip")
        ]
        assert {
            request.destination_relative_path.split("/")[2] for request in population_requests
        } == expected_levels
        assert all(len(request.geographic_levels) == 1 for request in population_requests)
        assert not any("census_state_population_totals_" in path for path in paths)
    else:
        assert {
            request.geography_level.value
            for request in requests
            if isinstance(request, CensusFileRequest)
        } == expected_levels
        assert not any(path.startswith("nhgis/") for path in paths)

    needs_1980_boundaries = year == 1980 and level == "tracts"
    assert any(path.startswith("tiger_1992/") for path in paths) == needs_1980_boundaries
    assert any(path.startswith("census_1990_blocks/") for path in paths) == (
        year == 1990 and level == "blocks"
    )
    assert not any("diagnostic_" in path or "stf1a" in path for path in paths)
    assert not any("metro_membership" in path for path in paths)
    for other_year in {1980, 1990, 2000, 2010, 2020} - {year}:
        assert not any(f"/{other_year}/" in path for path in paths)
        assert not any(f"56_{other_year}_" in path for path in paths)


@pytest.mark.parametrize(
    "settings",
    [
        {"census_geography_levels": []},
        {"census_geography_levels": ["tract"]},
        {"census_geography_levels": ["places"]},
        {"census_geography_levels": ["states"]},
        {"census_geography_years": []},
        {"census_geography_years": [2021]},
        {"study_area_type": "cities"},
        {"study_area_vintage": 2015},
    ],
)
def test_invalid_selection_values_are_rejected(settings):
    with pytest.raises(ValueError):
        PipelineConfig(**settings)


@pytest.mark.parametrize(
    "settings,message",
    [
        (
            {
                "census_geography_levels": ["blocks", "block_groups"],
                "census_geography_years": [1980],
            },
            "No supported node boundaries",
        ),
        ({"study_area_type": "max_city", "study_area_vintage": 1990}, "max_city requires"),
    ],
)
def test_unsupported_combinations_fail_before_creating_raw_files(tmp_path, settings, message):
    config = PipelineConfig(raw_data_directory=tmp_path / "raw", **settings)

    with pytest.raises(ValueError, match=message):
        retrieve_raw_data(config, tmp_path)

    assert not config.raw_data_directory.exists()


@pytest.mark.parametrize(
    "filename", ["example.yaml", "replication.yaml", "small_example.yaml", "modern_population.yaml"]
)
def test_shipped_yaml_files_select_valid_inputs(filename):
    from pathlib import Path

    config = load_configuration(Path(__file__).parents[1] / "configs" / filename)
    requests = build_raw_file_requests(config)
    selected = filter_raw_file_requests(requests, config.file_path_patterns)

    assert selected
    if filename == "replication.yaml":
        assert len(selected) == 1238
    elif filename == "small_example.yaml":
        assert len(selected) == 4
