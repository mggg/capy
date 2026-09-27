"""Graph population filtering, deterministic polygon connections, and archive publication."""

from io import StringIO
from itertools import combinations
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import networkx as nx
import pandas as pd
import pytest
from capy_core.assign_study_areas.run_assignment import assign_study_areas
from capy_core.build_graphs.construct_graph import (
    build_connected_graph,
    report_unexpected_graph_warning,
)
from capy_core.build_graphs.graph_archives import read_graph_from_archive
from capy_core.build_graphs.run_build import build_graph_archives
from capy_core.derived_file_paths import build_join_output_paths, build_population_output_path
from capy_core.geography_types import GeographyLevel
from capy_core.pipeline_config import load_configuration
from gerrychain import Graph
from shapely.geometry import box


def sample_units():
    return gpd.GeoDataFrame(
        {
            "GEOID": ["10001000100", "10001000200", "10001000300", "10001000400"],
            "state": ["10"] * 4,
            "county": ["001"] * 4,
            "TOTPOP": [10, 7, 20, 4],
            "WHITE": [5, 0, 10, 1],
            "BLACK": [3, 0, 8, 1],
            "POC": [5, 7, 10, 3],
            "geometry": [box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1), box(3, 0, 4, 1)],
        },
        crs="ESRI:102003",
    )


def test_filter_preserves_other_residents_in_accounting_and_connects_remaining_polygons():
    units_df = sample_units()
    before_df = units_df.copy()
    graph, removed_df = build_connected_graph(units_df)

    assert set(graph) == {"10001000100", "10001000300", "10001000400"}
    assert graph.edges["10001000300", "10001000400"]["artificial"] is False
    assert graph.edges["10001000100", "10001000300"] == {
        "artificial": True,
        "connection_distance_m": 1.0,
        "shared_perim": 0.0,
    }
    assert removed_df.TOTPOP.tolist() == [7]
    assert removed_df.WHITE.sum() + removed_df.BLACK.sum() == 0
    assert graph.graph["input_population"]["TOTPOP"] == 41
    assert graph.graph["retained_population"]["TOTPOP"] == 34
    assert graph.graph["removed_population"]["POC"] == 7
    assert graph.graph["initial_component_count"] == 2
    assert graph.nodes["10001000100"]["centroid_x"] == 0.5
    assert graph.nodes["10001000100"]["centroid_y"] == 0.5
    pd.testing.assert_frame_equal(units_df, before_df)


def test_polygon_distances_and_ties_produce_an_order_independent_minimum_spanning_tree():
    units_df = sample_units().assign(WHITE=1)
    units_df.POC = units_df.TOTPOP - units_df.WHITE
    units_df.geometry = [box(0, 0, 1, 20), box(2, 0, 3, 1), box(4, 0, 5, 1), box(2, 2, 3, 3)]
    graph, _ = build_connected_graph(units_df)
    reordered, _ = build_connected_graph(units_df.iloc[::-1])
    assert nx.utils.graphs_equal(graph, reordered)

    complete_graph = nx.Graph()
    polygons = units_df.set_index("GEOID").geometry
    for first_id, second_id in combinations(polygons.index, 2):
        complete_graph.add_edge(
            first_id, second_id, weight=polygons[first_id].distance(polygons[second_id])
        )

    expected_weight = nx.minimum_spanning_tree(complete_graph).size(weight="weight")
    assert graph.size(weight="connection_distance_m") == expected_weight
    assert set(graph.edges) == {
        ("10001000100", "10001000200"),
        ("10001000100", "10001000400"),
        ("10001000200", "10001000300"),
    }


@pytest.mark.parametrize("case", ["single", "empty", "filtered"])
def test_single_and_empty_graphs_have_no_artificial_connections(case):
    units_df = sample_units().iloc[:1].copy()
    if case == "empty":
        units_df = units_df.iloc[:0]
    elif case == "filtered":
        units_df.WHITE = 0
        units_df.BLACK = 0
        units_df.POC = units_df.TOTPOP

    graph, removed_df = build_connected_graph(units_df)
    assert len(graph) == (1 if case == "single" else 0)
    assert graph.number_of_edges() == 0
    assert graph.graph["artificial_edge_count"] == 0
    assert len(removed_df) == (1 if case == "filtered" else 0)


@pytest.fixture
def graph_run(tmp_path):
    config = load_configuration(Path("code/configs/small_example.yaml"))
    config.joined_geography_directory = tmp_path / "joined"
    config.study_area_directory = tmp_path / "areas"
    config.graph_archive_directory = tmp_path / "graphs"
    units_df = sample_units()
    counties_df = units_df.iloc[[0, 1]].copy()
    counties_df.GEOID = ["10001", "10003"]
    counties_df.county = ["001", "003"]
    counties_df["NAME"] = ["Selected county", "Empty county"]
    counties_df.geometry = [box(-1, -1, 5, 2), box(10, 10, 11, 11)]

    for level, population_df in (
        (GeographyLevel.COUNTY, counties_df),
        (GeographyLevel.TRACT, units_df),
    ):
        population_path = build_population_output_path(2020, level, "10")
        matched, unmatched_population, unmatched_boundaries = build_join_output_paths(
            population_path
        )
        matched_path = config.joined_geography_directory / matched
        matched_path.parent.mkdir(parents=True)
        population_df.assign(CENSUS_YEAR=2020, GEOGRAPHY_LEVEL=level.value).to_parquet(matched_path)
        pd.DataFrame({"GEOID": []}).to_parquet(
            config.joined_geography_directory / unmatched_population
        )
        gpd.GeoDataFrame({"GEOID": [], "geometry": []}, crs=units_df.crs).to_parquet(
            config.joined_geography_directory / unmatched_boundaries
        )

    assign_study_areas(config, tmp_path)
    return config


def test_archive_roundtrip_accounting_and_failed_rerun_removes_stale_outputs(graph_run, tmp_path):
    summary_df = build_graph_archives(graph_run, tmp_path).set_index("study_area_id")
    assert summary_df.status.to_dict() == {
        "county_10001": "ready",
        "county_10003": "no_units_selected",
    }
    archive_path = graph_run.graph_archive_directory / "county_2020_2020_tracts.zip"
    saved_bytes = archive_path.read_bytes()
    graph = read_graph_from_archive(archive_path, "graphs/county_10001.json")
    assert nx.is_connected(graph)
    assert graph.graph["county_codes"] == ["10001"]
    assert graph.graph["selected_place_code"] is None
    assert sum(attributes["TOTPOP"] for _, attributes in graph.nodes(data=True)) == 34

    with ZipFile(archive_path) as archive:
        # Also exercise GerryChain's filename reader on the exact archived JSON.
        json_path = tmp_path / "roundtrip.json"
        json_path.write_bytes(archive.read("graphs/county_10001.json"))
        assert nx.utils.graphs_equal(Graph.from_json(str(json_path)), graph)
        removed_df = pd.read_csv(StringIO(archive.read("removed_units/county_10001.csv").decode()))
        assert removed_df.TOTPOP.sum() == 7
        assert "graphs/county_10003.json" not in archive.namelist()

    build_graph_archives(graph_run, tmp_path)
    assert archive_path.read_bytes() == saved_bytes
    membership_path = (
        graph_run.study_area_directory
        / "county/2020/memberships/2020/tracts/DE_2020_memberships.parquet"
    )
    memberships_df = pd.read_parquet(membership_path)
    memberships_df.loc[0, "TOTPOP"] += 1
    memberships_df.to_parquet(membership_path)

    with pytest.raises(ValueError, match="membership identities and populations"):
        build_graph_archives(graph_run, tmp_path)

    assert not archive_path.exists()
    assert not (graph_run.graph_archive_directory / "county_2020_summary.parquet").exists()


def test_archive_rejects_changed_joined_populations(graph_run, tmp_path):
    joined_path = graph_run.joined_geography_directory / "2020/tracts/DE_2020_geography.parquet"
    units_df = gpd.read_parquet(joined_path)
    units_df.loc[0, "TOTPOP"] += 1
    units_df.loc[0, "POC"] += 1
    units_df.to_parquet(joined_path)

    with pytest.raises(ValueError, match="membership identities and populations"):
        build_graph_archives(graph_run, tmp_path)

    assert not list(graph_run.graph_archive_directory.glob("*.zip"))


@pytest.mark.parametrize("previously_empty", [False, True])
def test_newly_selected_polygon_cannot_be_hidden_by_saved_memberships(
    graph_run, tmp_path, previously_empty
):
    joined_path = graph_run.joined_geography_directory / "2020/tracts/DE_2020_geography.parquet"
    units_df = gpd.read_parquet(joined_path)
    added_unit_df = units_df.iloc[:1].copy()
    added_unit_df.GEOID = "10001000500"
    added_unit_df.geometry = [box(10, 10, 11, 11) if previously_empty else box(0, 1, 1, 1.5)]
    gpd.GeoDataFrame(pd.concat([units_df, added_unit_df]), crs=units_df.crs).to_parquet(joined_path)

    with pytest.raises(ValueError, match="current spatial membership"):
        build_graph_archives(graph_run, tmp_path)

    assert not list(graph_run.graph_archive_directory.glob("*.zip"))


@pytest.mark.parametrize(
    "column,dtype", [("study_area_type", "string"), ("definition_year", "Int64")]
)
def test_missing_definition_identity_is_rejected(graph_run, tmp_path, column, dtype):
    definition_path = graph_run.study_area_directory / "county/2020/definitions.parquet"
    definitions_df = gpd.read_parquet(definition_path)
    definitions_df[column] = pd.Series([pd.NA] * len(definitions_df), dtype=dtype)
    definitions_df.to_parquet(definition_path)

    with pytest.raises(ValueError, match="must match the configured"):
        build_graph_archives(graph_run, tmp_path)


def test_fully_filtered_area_keeps_population_accounting_without_a_graph(graph_run, tmp_path):
    joined_path = graph_run.joined_geography_directory / "2020/tracts/DE_2020_geography.parquet"
    units_df = gpd.read_parquet(joined_path)
    units_df.WHITE = 0
    units_df.BLACK = 0
    units_df.POC = units_df.TOTPOP
    units_df.to_parquet(joined_path)
    assign_study_areas(graph_run, tmp_path)
    summary_df = build_graph_archives(graph_run, tmp_path).set_index("study_area_id")

    assert summary_df.loc["county_10001", "status"] == "no_units_after_population_filter"
    assert summary_df.loc["county_10001", "removed_TOTPOP"] == 41
    assert summary_df.loc["county_10001", "retained_TOTPOP"] == 0
    with ZipFile(graph_run.graph_archive_directory / "county_2020_2020_tracts.zip") as archive:
        assert not any(name.startswith("graphs/") for name in archive.namelist())
        assert "removed_units/county_10001.csv" in archive.namelist()


@pytest.mark.parametrize("overlap_width,expect_warning", [(1e-6, False), (0.1, True)])
def test_known_overlap_is_silent_only_while_microscopic(overlap_width, expect_warning):
    import warnings

    units_df = sample_units().iloc[[0, 2]].copy()
    units_df.GEOID = ["G3600050", "G3600610"]
    units_df.geometry = [box(0, 0, 1, 1), box(1 - overlap_width, 0, 2, 1)]

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        graph, _ = build_connected_graph(units_df)

    overlap_warnings = [warning for warning in recorded if "Found overlaps" in str(warning.message)]
    assert bool(overlap_warnings) == expect_warning
    assert graph.edges["G3600050", "G3600610"]["artificial"] is False
    assert sum(attributes["TOTPOP"] for _, attributes in graph.nodes(data=True)) == 30


def test_mixed_overlap_warning_keeps_unknown_pairs_visible():
    units_df = sample_units().iloc[[0, 2, 3]].copy()
    units_df.GEOID = ["G3600050", "G3600610", "unrecognized_unit"]
    units_df.geometry = [box(0, 0, 1, 1), box(1 - 1e-6, 0, 2, 1), box(-1, 0, 1e-6, 1)]

    with pytest.warns(UserWarning, match="Found overlaps") as recorded:
        build_connected_graph(units_df)

    assert len(recorded) == 1
    assert "unrecognized_unit" in str(recorded[0].message)
    assert "G3600610" not in str(recorded[0].message)


def test_unexpected_overlap_respects_gerrychain_module_error_filter():
    import warnings

    units_df = sample_units().iloc[[0, 2]].copy()
    units_df.geometry = [box(0, 0, 1, 1), box(0.9, 0, 2, 1)]

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "error", category=UserWarning, module=r"gerrychain\.graph\.adjacency"
        )

        with pytest.raises(UserWarning, match="Found overlaps"):
            build_connected_graph(units_df)


@pytest.mark.parametrize(
    "message",
    [
        "An unrelated graph warning",
        "Found overlaps among the given polygons. Indices of overlaps: changed upstream format",
    ],
)
def test_other_warning_text_is_passed_through(message):
    import warnings

    graph_warning = warnings.WarningMessage(UserWarning(message), UserWarning, "example.py", 12)

    with pytest.warns(UserWarning) as recorded:
        report_unexpected_graph_warning(graph_warning, sample_units())

    assert len(recorded) == 1
    assert str(recorded[0].message) == message
