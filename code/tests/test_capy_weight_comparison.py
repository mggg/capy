"""Limiting Capy retains within-unit interactions for isolated groups."""

import numpy as np
import pytest
from capy_metrics import aspatial_capy, capy
from national_figures.compare_capy_weights import limiting_quadratic_capy
from scipy import sparse


def test_capy_neighbor_limit_retains_isolated_group_fraction():
    adjacency = sparse.csr_array([[0, 1, 0], [1, 0, 0], [0, 0, 0]])
    first = np.array([0.0, 0.0, 2.0])
    second = np.array([2.0, 3.0, 1.0])
    expected = (2 / 3 + 1) / 2
    assert limiting_quadratic_capy(adjacency, first, second) == pytest.approx(expected)
    assert capy(adjacency, first, second, lam=1e12) == pytest.approx(expected)
    assert limiting_quadratic_capy(sparse.csr_array((3, 3)), first, second) == aspatial_capy(
        first, second
    )


def test_weight_preparation_rejects_missing_ranked_definitions(tmp_path, monkeypatch):
    import pandas as pd
    from national_figures import compare_capy_weights as preparation
    from national_pipeline.geography_types import GeographyLevel
    from national_pipeline.pipeline_config import PipelineConfig

    definitions_df = pd.DataFrame(
        {"study_area_id": ["other"], "name": ["Other"], "definition_population": [200000]}
    )
    summary_df = pd.DataFrame(
        {"study_area_id": ["missing"], "retained_TOTPOP": [300000], "status": ["ready"]}
    )
    monkeypatch.setattr(pd, "read_parquet", lambda *args, **kwargs: definitions_df)
    monkeypatch.setattr(preparation, "read_graph_selection_summary", lambda *args: summary_df)
    monkeypatch.setattr(
        preparation,
        "read_graph_from_archive",
        lambda *args: pytest.fail("Definition validation must precede graph reads"),
    )
    with pytest.raises(ValueError, match="lack study-area definitions"):
        preparation.run_capy_weight_comparison(
            PipelineConfig(
                study_area_type="cbsa",
                census_geography_years=(2020,),
                census_geography_levels=(GeographyLevel.TRACT,),
            ),
            tmp_path,
            tmp_path / "result",
        )
    assert not (tmp_path / "result").exists()


@pytest.mark.parametrize("comparisons", [("white_poc",), ("white_black", "white_poc")])
def test_weight_plot_filters_to_tracts_and_renders_each_comparison(
    comparisons, tmp_path, monkeypatch
):
    from unittest.mock import Mock

    import pandas as pd
    from national_figures import plot_capy_weights
    from national_figures.plot_capy_weights import plot_capy_weight_comparison
    from national_pipeline.pipeline_config import PipelineConfig

    scores_df = pd.DataFrame(
        [
            {
                "study_area_id": "metro",
                "population_comparison": comparison,
                "census_year": 2000,
                "geography_level": level,
                "zero_rank": 3.0,
                "unit_rank": 1.0,
                "limit_rank": 2.0,
            }
            for comparison in comparisons
            for level in ("tracts", "block_groups", "blocks", "counties")
        ]
    )
    scores_df.to_parquet(tmp_path / "capy_weights.parquet", index=False)
    config = PipelineConfig(study_area_type="cbsa", study_area_vintage=2010)
    save_plot = Mock(wraps=plot_capy_weights.save_plot)
    monkeypatch.setattr(plot_capy_weights, "save_plot", save_plot)
    save_legend = Mock(wraps=plot_capy_weights.save_legend)
    monkeypatch.setattr(plot_capy_weights, "save_legend", save_legend)
    plot_capy_weight_comparison(config, tmp_path / "figures", tmp_path)
    image_files = {path.name for path in (tmp_path / "figures" / "capy_weights").iterdir()}
    assert image_files == {"neighbor_weights_legend.png"} | {
        f"{'WB' if comparison == 'white_black' else 'WPOC'}_CBSA10_2000_tract_capy_neighbor_weights.png"
        for comparison in comparisons
    }
    save_legend.assert_called_once()
    assert save_plot.call_count == len(comparisons)
    for saved_plot in save_plot.call_args_list:
        axes = saved_plot.args[0].axes[0]
        np.testing.assert_array_equal(axes.collections[0].get_offsets(), [[1, 3]])
        np.testing.assert_array_equal(axes.collections[1].get_offsets(), [[1, 2]])
    assert all(path.is_file() for path in (tmp_path / "figures" / "capy_weights").iterdir())


def test_weight_preparation_reads_only_cbsa_tracts_for_every_configured_year(tmp_path, monkeypatch):
    import networkx as nx
    import pandas as pd
    from national_figures import compare_capy_weights as preparation
    from national_pipeline.geography_types import GeographyLevel
    from national_pipeline.pipeline_config import PipelineConfig
    from national_pipeline.population_table_columns import PopulationColumn

    config = PipelineConfig(
        study_area_type="cbsa",
        census_geography_years=(1980, 2020),
        census_geography_levels=(GeographyLevel.TRACT, GeographyLevel.BLOCK),
    )
    definitions_df = pd.DataFrame({"study_area_id": ["metro"], "name": ["Example"]})
    graph = nx.path_graph(2)
    for node in graph:
        graph.nodes[node].update(
            {
                PopulationColumn.NON_HISPANIC_WHITE: 4 + node,
                PopulationColumn.NON_HISPANIC_BLACK: 2,
                PopulationColumn.POC: 3,
            }
        )
    requests = []

    def read_summary(path, year, level):
        assert path.name == f"cbsa_2020_{year}_tracts.zip"
        requests.append((year, level))
        return pd.DataFrame(
            {
                "study_area_id": ["metro", "unavailable"],
                "retained_TOTPOP": [200000, None],
                "status": ["ready", "historical_coverage_unavailable"],
                "archive": [path.name, path.name],
                "graph_member": ["graphs/metro.json", None],
            }
        )

    with monkeypatch.context() as patch:
        patch.setattr(pd, "read_parquet", lambda *args, **kwargs: definitions_df)
        patch.setattr(preparation, "read_graph_selection_summary", read_summary)
        patch.setattr(preparation, "read_graph_from_archive", lambda *args: graph)
        preparation.run_capy_weight_comparison(config, tmp_path, tmp_path / "results")

    assert set(requests) == {
        (1980, GeographyLevel.TRACT),
        (2020, GeographyLevel.TRACT),
    }
    scores_df = pd.read_parquet(tmp_path / "results/capy_weights.parquet")
    assert len(scores_df) == 4
    assert not scores_df.duplicated(
        ["study_area_id", "census_year", "geography_level", "population_comparison"]
    ).any()
    assert set(scores_df.population_comparison) == {"white_black", "white_poc"}
    assert scores_df[["zero_rank", "unit_rank", "limit_rank"]].eq(1).all().all()


@pytest.mark.parametrize("area_type, levels", [("max_city", ("tracts",)), ("cbsa", ("blocks",))])
def test_weight_comparison_rejects_out_of_scope_configs_before_io(
    area_type, levels, tmp_path, monkeypatch
):
    import pandas as pd
    from national_figures.compare_capy_weights import run_capy_weight_comparison
    from national_figures.plot_capy_weights import plot_capy_weight_comparison
    from national_pipeline.pipeline_config import PipelineConfig

    config = PipelineConfig(study_area_type=area_type, census_geography_levels=levels)
    monkeypatch.setattr(
        pd, "read_parquet", lambda *args, **kwargs: pytest.fail("Must reject before I/O")
    )
    for operation in (run_capy_weight_comparison, plot_capy_weight_comparison):
        with pytest.raises(ValueError, match="CBSAs with tracts selected"):
            operation(config, tmp_path, tmp_path)


def test_weight_plot_rejects_saved_results_without_tracts(tmp_path):
    import pandas as pd
    from national_figures.plot_capy_weights import plot_capy_weight_comparison
    from national_pipeline.pipeline_config import PipelineConfig

    pd.DataFrame({"geography_level": ["blocks"]}).to_parquet(tmp_path / "capy_weights.parquet")
    with pytest.raises(ValueError, match="one finite score"):
        plot_capy_weight_comparison(
            PipelineConfig(study_area_type="cbsa"), tmp_path / "plots", tmp_path
        )
    assert not (tmp_path / "plots").exists()
