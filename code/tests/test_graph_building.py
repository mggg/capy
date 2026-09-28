"""Graph population filtering, deterministic polygon connections, and archive publication."""

from io import StringIO
from itertools import combinations
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import networkx as nx
import pandas as pd
import pytest
from gerrychain import Graph
from national_pipeline.assign_study_areas.run_assignment import assign_study_areas
from national_pipeline.build_graphs.construct_graph import (
    build_connected_graph,
    report_unexpected_graph_warning,
)
from national_pipeline.build_graphs.graph_archives import read_graph_from_archive
from national_pipeline.build_graphs.run_build import build_graph_archives
from national_pipeline.derived_file_paths import (
    build_join_output_paths,
    build_population_output_path,
)
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import load_configuration
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


def test_archive_roundtrip_reuses_completed_graphs_and_failed_rerun_keeps_archives(
    graph_run, tmp_path, monkeypatch
):
    summary_df = build_graph_archives(graph_run, tmp_path).set_index("study_area_id")
    assert summary_df.status.to_dict() == {
        "county_10001": "ready",
        "county_10003": "no_units_selected",
    }
    archive_path = graph_run.graph_archive_directory / "county_2020_2020_tracts_part01.zip"
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

    def reject_rebuilding(*args, **kwargs):
        pytest.fail("Completed graphs should have been reused")

    with monkeypatch.context() as reuse_check:
        reuse_check.setattr(
            "national_pipeline.build_graphs.run_build.build_area_graph_files", reject_rebuilding
        )
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

    assert archive_path.read_bytes() == saved_bytes
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


@pytest.mark.parametrize("warn_on_polygon_overlaps", [True, False])
def test_parallel_graph_archive_matches_serial_bytes_and_accounting(
    graph_run, tmp_path, capfd, warn_on_polygon_overlaps
):
    import warnings

    county_path = graph_run.joined_geography_directory / "2020/counties/DE_2020_geography.parquet"
    counties_df = gpd.read_parquet(county_path)
    counties_df.loc[1, "geometry"] = counties_df.loc[0, "geometry"]
    counties_df.to_parquet(county_path)

    tract_path = graph_run.joined_geography_directory / "2020/tracts/DE_2020_geography.parquet"
    units_df = gpd.read_parquet(tract_path)
    units_df.loc[2, "geometry"] = box(0.5, 0, 3, 1)
    units_df.to_parquet(tract_path)
    assign_study_areas(graph_run, tmp_path)
    graph_run.warn_on_polygon_overlaps = warn_on_polygon_overlaps
    graph_run.max_parallel_graphs = 1

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        serial_summary_df = build_graph_archives(graph_run, tmp_path)

    assert any("Found overlaps" in str(warning.message) for warning in recorded) == (
        warn_on_polygon_overlaps
    )
    assert serial_summary_df.status.tolist() == ["ready", "ready"]
    archive_path = graph_run.graph_archive_directory / "county_2020_2020_tracts_part01.zip"
    serial_bytes = archive_path.read_bytes()
    capfd.readouterr()

    graph_run.max_parallel_graphs = 2
    graph_run.rebuild_graphs = True
    parallel_summary_df = build_graph_archives(graph_run, tmp_path)
    assert ("Found overlaps" in capfd.readouterr().err) == warn_on_polygon_overlaps

    pd.testing.assert_frame_equal(serial_summary_df, parallel_summary_df)
    assert archive_path.read_bytes() == serial_bytes
    assert not list(graph_run.graph_archive_directory.glob(".graph-build-*"))


def test_graph_worker_failure_cleans_temporary_files_and_does_not_publish(
    graph_run, tmp_path, monkeypatch
):
    from national_pipeline.build_graphs import run_build

    read_memberships = run_build.read_selection_memberships

    def change_population_after_membership_validation(*args):
        validated_tables = read_memberships(*args)
        joined_path = graph_run.joined_geography_directory / "2020/tracts/DE_2020_geography.parquet"
        units_df = gpd.read_parquet(joined_path)
        units_df.loc[0, "TOTPOP"] += 1
        units_df.loc[0, "POC"] += 1
        units_df.to_parquet(joined_path)

        return validated_tables

    monkeypatch.setattr(
        run_build, "read_selection_memberships", change_population_after_membership_validation
    )
    graph_run.max_parallel_graphs = 2

    with pytest.raises(ValueError, match="Joined polygons do not reproduce"):
        build_graph_archives(graph_run, tmp_path)

    assert not list(graph_run.graph_archive_directory.iterdir())


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
    with ZipFile(
        graph_run.graph_archive_directory / "county_2020_2020_tracts_part01.zip"
    ) as archive:
        assert not any(name.startswith("graphs/") for name in archive.namelist())
        assert "removed_units/county_10001.csv" in archive.namelist()


@pytest.mark.parametrize(
    "overlap_width,expect_warning", [(1e-6, False), (0.0001, False), (0.000101, True)]
)
def test_overlap_warning_depends_on_area_not_geographic_ids(overlap_width, expect_warning):
    import warnings

    units_df = sample_units().iloc[[0, 2]].copy()
    units_df.GEOID = ["first_unit", "second_unit"]
    units_df.geometry = [box(0, 0, 1, 1), box(-1, 0, overlap_width, 1)]

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        graph, _ = build_connected_graph(units_df)

    overlap_warnings = [warning for warning in recorded if "Found overlaps" in str(warning.message)]
    assert bool(overlap_warnings) == expect_warning
    assert graph.edges["first_unit", "second_unit"]["artificial"] is False
    assert sum(attributes["TOTPOP"] for _, attributes in graph.nodes(data=True)) == 30


def test_mixed_overlap_warning_keeps_only_larger_pairs_visible():
    units_df = sample_units().iloc[[0, 2, 3]].copy()
    units_df.GEOID = ["first_unit", "tiny_overlap_unit", "larger_overlap_unit"]
    units_df.geometry = [box(0, 0, 1, 1), box(1 - 1e-6, 0, 2, 1), box(-1, 0, 0.1, 1)]

    with pytest.warns(UserWarning, match="Found overlaps") as recorded:
        build_connected_graph(units_df)

    assert len(recorded) == 1
    assert "larger_overlap_unit" in str(recorded[0].message)
    assert "tiny_overlap_unit" not in str(recorded[0].message)


def test_disabling_overlap_warnings_preserves_graph_and_unrelated_warnings(monkeypatch):
    import warnings

    units_df = sample_units().iloc[[0, 2]].copy()
    units_df.geometry = [box(0, 0, 1, 1), box(0.5, 0, 2, 1)]

    with pytest.warns(UserWarning, match="Found overlaps"):
        expected_graph, expected_removed_df = build_connected_graph(units_df)

    from_geodataframe = Graph.from_geodataframe

    def build_with_unrelated_warning(*args, **kwargs):
        warnings.warn("Unrelated graph warning", UserWarning)
        return from_geodataframe(*args, **kwargs)

    monkeypatch.setattr(Graph, "from_geodataframe", build_with_unrelated_warning)

    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        graph, removed_df = build_connected_graph(units_df, warn_on_polygon_overlaps=False)

    assert [str(warning.message) for warning in recorded] == ["Unrelated graph warning"]
    assert nx.utils.graphs_equal(graph, expected_graph)
    pd.testing.assert_frame_equal(removed_df, expected_removed_df)


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
        "Found overlaps among the given polygons. Indices of overlaps: {'unexpected_entry'}",
    ],
)
def test_other_warning_text_is_passed_through(message):
    import warnings

    graph_warning = warnings.WarningMessage(UserWarning(message), UserWarning, "example.py", 12)

    with pytest.warns(UserWarning) as recorded:
        report_unexpected_graph_warning(graph_warning, sample_units())

    assert len(recorded) == 1
    assert str(recorded[0].message) == message


def test_numbered_parts_preserve_metrics_and_missing_last_part_is_rebuilt(graph_run, tmp_path):
    import shutil

    from national_pipeline.build_graphs.archive_inventory import read_graph_selection_summary
    from national_pipeline.build_graphs.archive_parts import publish_graph_archive_parts
    from national_pipeline.compute_metrics.run_metrics import compute_metrics

    build_graph_archives(graph_run, tmp_path)
    graph_run.metric_results_directory = tmp_path / "metrics"
    expected_scores_df = compute_metrics(graph_run, tmp_path)
    base_path = graph_run.graph_archive_directory / "county_2020_2020_tracts.zip"
    first_part_path = base_path.with_stem(f"{base_path.stem}_part01")
    shutil.copyfile(first_part_path, base_path)
    source_bytes = base_path.read_bytes()

    with ZipFile(base_path) as source:
        expected_members = {
            name: source.read(name) for name in source.namelist() if name != "summary.csv"
        }

    part_summary_df = publish_graph_archive_parts(base_path, base_path, target_size_bytes=1)
    assert base_path.read_bytes() == source_bytes
    assert part_summary_df.archive.nunique() == 2
    observed_members = {}

    for filename in part_summary_df.archive.unique():
        with ZipFile(base_path.parent / filename) as part:
            for name in part.namelist():
                if name != "summary.csv":
                    assert name not in observed_members
                    observed_members[name] = part.read(name)

    assert observed_members == expected_members
    base_path.unlink()
    pd.testing.assert_frame_equal(compute_metrics(graph_run, tmp_path), expected_scores_df)
    last_part_path = base_path.parent / part_summary_df.archive.iloc[-1]
    last_part_path.unlink()

    with pytest.raises(ValueError, match="Incomplete"):
        read_graph_selection_summary(base_path, 2020, GeographyLevel.TRACT)

    rebuilt_df = build_graph_archives(graph_run, tmp_path)
    assert len(rebuilt_df) == 2
    assert rebuilt_df.archive.nunique() == 1
    pd.testing.assert_frame_equal(compute_metrics(graph_run, tmp_path), expected_scores_df)


def test_failed_repackaging_preserves_source_and_previous_parts(graph_run, tmp_path, monkeypatch):
    import shutil

    from national_pipeline.build_graphs import archive_parts

    build_graph_archives(graph_run, tmp_path)
    base_path = graph_run.graph_archive_directory / "county_2020_2020_tracts.zip"
    part_path = base_path.with_stem(f"{base_path.stem}_part01")
    shutil.copyfile(part_path, base_path)
    original_bytes = base_path.read_bytes()

    def reject_changed_member(*args):
        raise ValueError("Repackaging changed a member")

    monkeypatch.setattr(archive_parts, "check_repackaged_members", reject_changed_member)

    with pytest.raises(ValueError, match="Repackaging changed"):
        archive_parts.publish_graph_archive_parts(base_path, base_path)

    assert base_path.read_bytes() == original_bytes
    assert part_path.read_bytes() == original_bytes
    assert not list(base_path.parent.glob(".graph-package-*"))


def test_part_numbers_above_99_are_read_in_numeric_order(tmp_path):
    from national_pipeline.build_graphs.archive_inventory import read_graph_selection_summary
    from national_pipeline.build_graphs.build_area_graph import GraphStatus

    base_path = tmp_path / "county_2020_2020_tracts.zip"

    for number in range(1, 101):
        summary_df = pd.DataFrame(
            [
                {
                    "study_area_id": f"county_{number:05d}",
                    "census_year": 2020,
                    "geography_level": GeographyLevel.TRACT,
                    "status": GraphStatus.NO_UNITS_SELECTED,
                    "graph_member": None,
                    "archive_part_count": 100,
                }
            ]
        )

        with ZipFile(base_path.with_stem(f"{base_path.stem}_part{number:02d}"), "w") as archive:
            archive.writestr("summary.csv", summary_df.to_csv(index=False))

    summary_df = read_graph_selection_summary(base_path, 2020, GeographyLevel.TRACT)
    assert summary_df.study_area_id.tolist() == [f"county_{number:05d}" for number in range(1, 101)]
