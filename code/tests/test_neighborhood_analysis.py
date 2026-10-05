"""Explicit neighborhood ranks and historical buffers preserve tract selection semantics."""

import geopandas as gpd
import networkx as nx
import pandas as pd
from experiments.neighborhood_change.observed_dispersion import (
    CityDefinition,
    CityTracts,
    NeighborhoodDefinition,
    analyze_city_neighborhoods,
)
from shapely.geometry import box


def test_neighborhood_ranks_do_not_depend_on_definition_order():
    tract_ids = ["a", "b", "bridge", "d", "e"]
    black_population = [90, 90, 10, 90, 90]
    graph = nx.path_graph(tract_ids)
    tracts_df = gpd.GeoDataFrame(
        {"BLACK": black_population, "WHITE": [100 - count for count in black_population]},
        geometry=[box(index, 0, index + 1, 1) for index in range(5)],
        index=tract_ids,
        crs="ESRI:102003",
    )

    for index, tract_id in enumerate(tract_ids):
        graph.nodes[tract_id].update(
            BLACK=black_population[index],
            WHITE=100 - black_population[index],
            centroid_x=index + 0.5,
            centroid_y=0.5,
        )

    original_tracts_df = tracts_df.copy()
    city = CityDefinition(
        name="example",
        place_id="0000000",
        state_code="00",
        neighborhoods=(
            NeighborhoodDefinition(name="east", component_rank=1, reference_tract_id="d"),
            NeighborhoodDefinition(name="west", component_rank=0, reference_tract_id="a"),
        ),
    )
    city_tracts = CityTracts(graph=graph, tracts_df=tracts_df)
    east, west = analyze_city_neighborhoods(city, {1990: city_tracts, 2020: city_tracts}, 1)

    for result, name, core_ids in ((east, "east", {"d", "e"}), (west, "west", {"a", "b"})):
        assert set(result.scores_df.cluster) == {f"example_{name}"}
        assert len(result.scores_df) == 22
        assert set(result.memberships_df.buffer_steps) == set(range(11))
        assert set(result.maps_df.buffer_steps) == {1}
        assert set(result.maps_df.year) == {1990, 2020}
        selected_core_df = result.memberships_df.loc[result.memberships_df.buffer_steps.eq(0)]
        assert set(selected_core_df.geographic_id) == core_ids
        assert result.scores_df.groupby("year").medoid.nunique().eq(1).all()

    pd.testing.assert_frame_equal(tracts_df, original_tracts_df)
