"""Neighborhood medoids and named-core checks preserve the experiment's geographic meaning."""

import geopandas as gpd
import networkx as nx
import pandas as pd
import pytest
from experiments.neighborhood_change import observed_dispersion
from experiments.neighborhood_change.plot_observed_dispersion import plot_neighborhood_history
from national_pipeline.pipeline_config import PipelineConfig
from shapely.geometry import box


def test_philadelphia_history_exports_choropleths_and_radial_views(tmp_path):
    maps_df = gpd.GeoDataFrame(
        {
            "year": [1980, 2020],
            "GEOID": ["a", "b"],
            "black_share": [0.7, 0.8],
            "radial_x": [0.0, 0.0],
            "radial_y": [0.0, 0.0],
            "is_medoid": [True, True],
        },
        geometry=[box(0, 0, 1, 1), box(0, 0, 1, 1)],
        crs="ESRI:102003",
    )
    core_memberships_df = pd.DataFrame({"year": [1980, 2020], "geographic_id": ["a", "b"]})
    plot_neighborhood_history(
        "philadelphia_germantown", maps_df, core_memberships_df, pd.DataFrame(), tmp_path
    )

    assert {path.name for path in tmp_path.glob("*.png")} == {
        f"{kind}_{year}_black_share.png"
        for kind in ("choro", "radial")
        for year in (1980, 2020)
    }


def test_population_medoid_uses_full_city_paths_and_sorted_ties():
    graph = nx.path_graph(["a", "outside", "b", "c"])
    nx.set_node_attributes(graph, 1, "BLACK")
    assert observed_dispersion.find_black_population_medoid(graph, ["c", "b", "a"]) == "b"
    assert observed_dispersion.find_black_population_medoid(graph, ["b", "a"]) == "a"


@pytest.mark.parametrize("exchange_component_ranks", [False, True])
def test_named_core_reference_tracts_prevent_silent_neighborhood_exchange(
    tmp_path, monkeypatch, exchange_component_ranks
):
    city_code = "1714000"
    city = next(city for city in observed_dispersion.CITIES if city.place_id == city_code)
    reference_tracts = {
        definition.name: definition.reference_tract_id for definition in city.neighborhoods
    }
    node_ids = [
        reference_tracts["south_side"],
        "south",
        "bridge",
        reference_tracts["austin"],
        "west",
    ]
    graph = nx.path_graph(node_ids)
    black_population = [90, 90, 10, 90, 90]
    tracts_df = gpd.GeoDataFrame(
        {
            "GEOID": node_ids,
            "BLACK": black_population,
            "WHITE": [100 - count for count in black_population],
        },
        geometry=[box(index, 0, index + 1, 1) for index in range(5)],
        index=node_ids,
        crs="ESRI:102003",
    )

    for index, node in enumerate(node_ids):
        graph.nodes[node].update(
            BLACK=black_population[index],
            WHITE=100 - black_population[index],
            centroid_x=index + 0.5,
            centroid_y=0.5,
        )

    monkeypatch.setattr(observed_dispersion, "CITIES", (city,))
    monkeypatch.setattr(
        observed_dispersion,
        "read_city_tracts",
        lambda *_: observed_dispersion.CityTracts(graph=graph, tracts_df=tracts_df),
    )

    if exchange_component_ranks:
        cores = observed_dispersion.select_black_clusters(graph)
        monkeypatch.setattr(observed_dispersion, "select_black_clusters", lambda _: cores[::-1])

        with pytest.raises(ValueError, match="south_side core lacks reference tract"):
            observed_dispersion.run_observed_dispersion(
                PipelineConfig(), tmp_path, tmp_path / "out"
            )

        assert not (tmp_path / "out").exists()
        return

    observed_dispersion.run_observed_dispersion(PipelineConfig(), tmp_path, tmp_path / "out")
    scores_df = pd.read_parquet(tmp_path / "out/cluster_scores.parquet")
    assert len(scores_df) == 2 * 5 * 11
    assert set(scores_df.cluster) == {"chicago_south_side", "chicago_austin"}
    assert scores_df.groupby(["cluster", "year"]).medoid.nunique().eq(1).all()
    assert (tmp_path / "out/cluster_cores.parquet").exists()
