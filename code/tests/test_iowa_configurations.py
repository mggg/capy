"""Iowa results preserve scored adjacency and expose caller-owned drawing axes."""

import random

import geopandas as gpd
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from experiments.iowa_configurations import county_configurations, plot_county_configurations
from matplotlib.collections import LineCollection
from national_pipeline.derived_file_paths import (
    build_join_output_paths,
    build_population_output_path,
)
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import PipelineConfig
from shapely.geometry import box


def test_iowa_arrangements_preserve_graph_and_respect_component_constraints():
    graph = nx.grid_2d_graph(5, 5)
    graph = nx.relabel_nodes(graph, {node: str(node) for node in graph})
    nx.set_node_attributes(graph, 100, "TOTPOP")

    for arrangement in county_configurations.CountyArrangement:
        selected_counties = county_configurations.select_county_arrangement(
            graph, 0.3, arrangement, random.Random(42)
        )
        assert selected_counties is not None
        first_group_graph = graph.subgraph(selected_counties)

        if arrangement == county_configurations.CountyArrangement.ISOLATED:
            assert first_group_graph.number_of_edges() == 0
        elif arrangement == county_configurations.CountyArrangement.CLUSTERED:
            assert nx.is_connected(first_group_graph)
        else:
            assert 2 <= nx.number_connected_components(first_group_graph) <= 4

    assert all(attributes == {"TOTPOP": 100} for _, attributes in graph.nodes(data=True))


def test_iowa_computation_saves_adjacency_and_plotting_does_not_rebuild_it(tmp_path, monkeypatch):
    config = PipelineConfig()
    population_path = build_population_output_path(2020, GeographyLevel.COUNTY, "19")
    geography_path = (
        tmp_path / config.joined_geography_directory / build_join_output_paths(population_path)[0]
    )
    geography_path.parent.mkdir(parents=True)
    counties_df = gpd.GeoDataFrame(
        {
            "GEOID": [f"county_{index}" for index in range(99)],
            "TOTPOP": [100] * 99,
            "WHITE": [60] * 99,
            "BLACK": [40] * 99,
            "POC": [40] * 99,
        },
        geometry=[
            box(column, row, column + 1, row + 1) for row in range(9) for column in range(11)
        ],
        crs="ESRI:102003",
    )
    counties_df.to_parquet(geography_path)
    built_graphs = []
    build_graph = county_configurations.build_connected_graph

    def record_graph(*args, **kwargs):
        graph, removed_df = build_graph(*args, **kwargs)
        built_graphs.append(graph)
        return graph, removed_df

    monkeypatch.setattr(county_configurations, "build_connected_graph", record_graph)
    result_directory = tmp_path / "results"
    county_configurations.run_iowa_experiments(
        config, tmp_path, result_directory, samples_per_share=1, share_count=2, seed=42
    )
    assert len(built_graphs) == 1
    edges_df = pd.read_parquet(result_directory / "iowa_edges.parquet")
    expected_edges = {frozenset(edge) for edge in built_graphs[0].edges}
    assert {
        frozenset(edge) for edge in edges_df.itertuples(index=False, name=None)
    } == expected_edges

    def reject_graph_rebuild(*args, **kwargs):
        raise AssertionError("Rendering must use saved adjacency")

    monkeypatch.setattr(county_configurations, "build_connected_graph", reject_graph_rebuild)
    monkeypatch.setattr(
        plot_county_configurations, "build_connected_graph", reject_graph_rebuild, raising=False
    )
    exports = []

    def inspect_export(figure, output_path):
        axes = figure.axes[0]

        if output_path.name.startswith("dualgraph_"):
            drawn_edges = next(
                item for item in axes.collections if isinstance(item, LineCollection)
            )
            assert len(drawn_edges.get_segments()) == len(expected_edges)

        axes.set_yticks([0, 0.5, 1])
        np.testing.assert_array_equal(axes.get_yticks(), [0, 0.5, 1])
        exports.append(output_path)
        plt.close(figure)

    monkeypatch.setattr(plot_county_configurations, "save_plot", inspect_export)
    plot_county_configurations.plot_iowa_experiments(result_directory, tmp_path / "figures")
    assert len(exports) == 9
