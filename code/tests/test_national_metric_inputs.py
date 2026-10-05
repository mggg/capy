"""National figures use configured pipeline scores and preserve complete history cohorts."""

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import pytest
from national_figures import plot_national_results, prepare_national_results
from national_pipeline.compute_metrics.metric_types import MetricName, PopulationComparison
from national_pipeline.geography_types import GeographyLevel, StudyAreaType
from national_pipeline.pipeline_config import PipelineConfig
from shapely.geometry import Point


@pytest.mark.parametrize("include_capy", [True, False])
def test_national_figures_use_pipeline_scores_without_reading_graphs(
    tmp_path, monkeypatch, include_capy
):
    config = PipelineConfig(
        study_area_type=StudyAreaType.CBSA,
        census_geography_years=(2020,),
        census_geography_levels=(GeographyLevel.TRACT,),
    )
    graph_summary_df = pd.DataFrame(
        [{"study_area_id": "cbsa_10000", "census_year": 2020, "geography_level": "tracts"}]
    )
    definitions_df = pd.DataFrame(
        [{"study_area_id": "cbsa_10000", "definition_population": 200000}]
    )
    rows = []

    for comparison in ("white_black", "white_poc"):
        for metric in prepare_national_results.HISTORY_METRICS:
            if metric == MetricName.CAPY and not include_capy:
                continue

            rows.append(
                {
                    **graph_summary_df.iloc[0].to_dict(),
                    "population_comparison": comparison,
                    "metric": metric.value,
                    "value": 0.6,
                    "undefined_reason": None,
                }
            )

    scores_df = pd.DataFrame(rows)
    monkeypatch.setattr(
        prepare_national_results,
        "read_national_figure_inputs",
        lambda *_: (scores_df, definitions_df, graph_summary_df),
    )
    if not include_capy:
        with pytest.raises(ValueError, match="run compute-metrics"):
            prepare_national_results.prepare_national_figure_data(
                config, tmp_path, tmp_path / "results"
            )

        assert not (tmp_path / "results").exists()
        return

    prepare_national_results.prepare_national_figure_data(config, tmp_path, tmp_path / "results")

    saved_scores_df = pd.read_parquet(tmp_path / "results/national_score_rows.parquet")
    pd.testing.assert_frame_equal(
        saved_scores_df.reset_index(drop=True),
        scores_df.reset_index(drop=True),
    )

    assert not (tmp_path / "results/capy_scores.parquet").exists()
    assert (tmp_path / "results/national_score_rows.parquet").exists()


@pytest.mark.parametrize("existing_outputs", [False, True])
def test_incomplete_histories_do_not_publish_any_prepared_tables(
    tmp_path, monkeypatch, existing_outputs
):
    config = PipelineConfig(
        population_comparisons=(PopulationComparison.WHITE_BLACK,),
        census_geography_years=(2020,),
        census_geography_levels=(GeographyLevel.TRACT,),
        metric_names=(MetricName.MORAN_ROW_STANDARDIZED, MetricName.CAPY),
    )
    graph_summary_df = pd.DataFrame(
        [{"study_area_id": "area_1", "census_year": 2020, "geography_level": "tracts"}]
    )
    definitions_df = pd.DataFrame(
        [{"study_area_id": "area_1", "name": "Original", "definition_population": 200000}]
    )
    scores_df = pd.DataFrame(
        [
            {
                **graph_summary_df.iloc[0].to_dict(),
                "population_comparison": "white_black",
                "metric": metric,
                "value": 0.6,
            }
            for metric in config.metric_names
        ]
    )
    monkeypatch.setattr(
        prepare_national_results,
        "read_national_figure_inputs",
        lambda *_: (scores_df, definitions_df, graph_summary_df),
    )
    output_directory = tmp_path / "prepared"
    previous_contents = {}

    if existing_outputs:
        prepare_national_results.prepare_national_figure_data(config, tmp_path, output_directory)
        previous_contents = {path.name: path.read_bytes() for path in output_directory.iterdir()}
        assert len(previous_contents) == 4

    definitions_df.loc[0, "name"] = "Changed"
    definitions_df.loc[0, "definition_population"] = 300000
    scores_df.loc[scores_df.metric.eq(MetricName.CAPY), "value"] = float("nan")

    with pytest.raises(ValueError, match="No complete score histories.*capy"):
        prepare_national_results.prepare_national_figure_data(config, tmp_path, output_directory)

    if existing_outputs:
        assert {
            path.name: path.read_bytes() for path in output_directory.iterdir()
        } == previous_contents
    else:
        assert not output_directory.exists()


def test_top_ten_use_population_and_identity_order_before_score_filtering(tmp_path, monkeypatch):
    config = PipelineConfig(
        population_comparisons=(PopulationComparison.WHITE_BLACK,),
        census_geography_years=(2020,),
        census_geography_levels=(GeographyLevel.TRACT,),
        metric_names=(MetricName.CAPY,),
    )
    definitions_df = (
        pd.DataFrame(
            {
                "study_area_id": [f"area_{number:02}" for number in range(13)],
                "definition_population": [
                    100000,
                    200000,
                    *range(300000, 1100000, 100000),
                    200000,
                    200000,
                    90000,
                ],
            }
        )
        .iloc[::-1]
        .reset_index(drop=True)
    )
    original_definitions_df = definitions_df.copy(deep=True)
    graph_summary_df = definitions_df[["study_area_id"]].assign(
        census_year=2020, geography_level="tracts"
    )
    scores_df = graph_summary_df.assign(
        population_comparison="white_black", metric="capy", value=0.6
    )
    scores_df.loc[scores_df.study_area_id.eq("area_09"), "value"] = float("nan")
    monkeypatch.setattr(
        prepare_national_results,
        "read_national_figure_inputs",
        lambda *_: (scores_df, definitions_df, graph_summary_df),
    )

    prepare_national_results.prepare_national_figure_data(config, tmp_path, tmp_path)
    top_10_df = pd.read_parquet(tmp_path / "top_10_metros.parquet")
    histories_df = pd.read_parquet(tmp_path / "trajectory_rows.parquet")
    eligible_areas_df = pd.read_parquet(tmp_path / "eligible_areas.parquet")

    assert list(top_10_df.study_area_id) == [
        "area_09",
        "area_08",
        "area_07",
        "area_06",
        "area_05",
        "area_04",
        "area_03",
        "area_02",
        "area_01",
        "area_10",
    ]
    assert "area_09" not in set(histories_df.study_area_id)
    assert "area_11" in set(eligible_areas_df.study_area_id)
    assert not {"area_00", "area_12"} & set(eligible_areas_df.study_area_id)
    pd.testing.assert_frame_equal(definitions_df, original_definitions_df)


def test_history_outputs_keep_cohorts_legends_and_filenames_together(tmp_path, monkeypatch):
    excluded_ids = {"cbsa_25940", "cbsa_29420", "cbsa_35100", "cbsa_39150", "cbsa_39460"}
    top_10_metro_ids = [f"cbsa_{number}" for number in range(10000, 10010)]
    negative_score_id = top_10_metro_ids[0]
    area_ids = [*top_10_metro_ids, *sorted(excluded_ids)]
    definitions_df = pd.DataFrame(
        {
            "study_area_id": area_ids,
            "name": [f"Metro {area_id}" for area_id in area_ids],
            "definition_population": [200000] * 10 + [150000] * len(excluded_ids),
        }
    )
    rows = []

    for comparison in PopulationComparison:
        for level in (GeographyLevel.TRACT, GeographyLevel.BLOCK_GROUP, GeographyLevel.BLOCK):
            years = [1980, 1990, 2000, 2010, 2020]

            if level != GeographyLevel.TRACT:
                years = years[1:]

            for area_id in sorted(excluded_ids | set(top_10_metro_ids)):
                for year in years:
                    for metric in prepare_national_results.HISTORY_METRICS:
                        rows.append(
                            {
                                "study_area_id": area_id,
                                "census_year": year,
                                "geography_level": level,
                                "population_comparison": comparison,
                                "metric": metric,
                                "value": (
                                    -0.4
                                    if area_id == negative_score_id
                                    and metric == MetricName.MORAN_ROW_STANDARDIZED
                                    else 0.5
                                ),
                            }
                        )

    scores_df = pd.DataFrame(rows)
    original_df = scores_df.copy(deep=True)
    mean_inputs_by_path = {}
    plot_paths = set()
    legend_paths = set()

    mean_inputs_by_axes = {}

    draw_history = plot_national_results.plot_score_history

    def record_plot(axes, trajectories_df, top_10_metros_df, config):
        mean_inputs_by_axes[axes] = trajectories_df.copy()
        return draw_history(axes, trajectories_df, top_10_metros_df, config)

    def record_export(figure, output_path):
        assert output_path not in plot_paths
        plot_paths.add(output_path)
        axes = figure.axes[0]

        if axes in mean_inputs_by_axes:
            mean_inputs_by_path[output_path] = mean_inputs_by_axes[axes]

        plt.close(figure)

    def record_legend(entries, output_path):
        legend_paths.add(output_path)

    monkeypatch.setattr(plot_national_results, "plot_score_history", record_plot)
    monkeypatch.setattr(plot_national_results, "save_plot", record_export)
    monkeypatch.setattr(plot_national_results, "save_legend", record_legend)
    graph_summary_df = scores_df[prepare_national_results.IDENTITY_COLUMNS].drop_duplicates()
    monkeypatch.setattr(
        prepare_national_results,
        "read_national_figure_inputs",
        lambda *_: (scores_df, definitions_df, graph_summary_df),
    )
    prepare_national_results.prepare_national_figure_data(
        PipelineConfig(
            study_area_type=StudyAreaType.CBSA,
            population_comparisons=(PopulationComparison.WHITE_BLACK,),
        ),
        tmp_path,
        tmp_path,
    )
    histories_df = pd.read_parquet(tmp_path / "trajectory_rows.parquet")
    plot_national_results.plot_national_figures(
        PipelineConfig(
            study_area_type=StudyAreaType.CBSA,
            population_comparisons=(PopulationComparison.WHITE_BLACK,),
        ),
        tmp_path / "figures",
        tmp_path,
    )
    tract_directory = tmp_path / "figures/history/WB_CBSA20_tract_histories"

    for metric in prepare_national_results.HISTORY_METRICS:
        all_areas_path = tract_directory / f"TRACT_{metric}_histories.png"
        assert all_areas_path in plot_paths
        assert tract_directory / "top_10_legend" in legend_paths
        assert set(mean_inputs_by_path[all_areas_path].study_area_id) == set(top_10_metro_ids)

    for output_path, plotted_df in mean_inputs_by_path.items():
        assert len(output_path.relative_to(tmp_path / "figures/history").parts) == 2
        assert output_path.parent / "individual_metro_legend" in legend_paths
        first_row = plotted_df.iloc[0]
        selected_df = histories_df.loc[
            histories_df.population_comparison.eq(first_row.population_comparison)
            & histories_df.geography_level.eq(first_row.geography_level)
            & histories_df.metric.eq(first_row.metric)
        ]
        pd.testing.assert_frame_equal(
            selected_df.reset_index(drop=True), plotted_df.reset_index(drop=True)
        )

        if output_path.parent != tract_directory:
            assert set(plotted_df.study_area_id) == excluded_ids | set(top_10_metro_ids)

    assert len(plot_paths) == 3 * len(prepare_national_results.HISTORY_METRICS)
    pd.testing.assert_frame_equal(scores_df, original_df)


@pytest.mark.parametrize("metric", [MetricName.CAPY, MetricName.ENTROPY_INDEX])
@pytest.mark.parametrize("level", ["tracts", "block_groups", "blocks"])
def test_history_draws_on_supplied_axes_and_returns_matching_legend_lines(metric, level):
    scores_df = pd.DataFrame(
        {
            "study_area_id": ["cbsa_10000", "cbsa_10000", "cbsa_30000", "cbsa_30000"],
            "census_year": [2000, 2010, 2000, 2010],
            "geography_level": [level] * 4,
            "metric": [metric] * 4,
            "value": [0.6, 0.8, 0.2, 0.4],
        }
    )
    # The missing area stays in the legend, in population order.
    top_10_metros_df = pd.DataFrame(
        {"study_area_id": ["cbsa_20000", "cbsa_10000"], "name": ["Missing", "Present"]}
    )
    config = PipelineConfig(census_geography_years=(2000, 2010))
    original_scores_df = scores_df.copy(deep=True)
    original_top_10_df = top_10_metros_df.copy(deep=True)
    figure, (unused_axes, axes) = plt.subplots(1, 2)
    open_figures = plt.get_fignums()

    try:
        top_10_handles, individual_and_mean_handles = plot_national_results.plot_score_history(
            axes, scores_df, top_10_metros_df, config
        )
        assert [label.get_text() for label in axes.get_xticklabels()] == ["2000", "2010"]

        if metric == MetricName.ENTROPY_INDEX:
            assert axes.get_ylim() == (0, 1)

        axes.set_xticks([2000, 2005, 2010], labels=["2000", "2005", "2010"])
        axes.set_ylim(-0.1, 1.1)
        figure.canvas.draw()

        assert plt.get_fignums() == open_figures
        assert len(figure.axes) == 2
        assert not unused_axes.lines
        assert list(axes.get_xticks()) == [2000, 2005, 2010]
        assert axes.get_ylim() == (-0.1, 1.1)
        assert [line.get_label() for line in top_10_handles] == ["Missing", "Present"]
        assert len(top_10_handles[0].get_xdata()) == 0
        assert list(top_10_handles[1].get_ydata()) == [0.6, 0.8]
        assert all(line in axes.lines for line in [*top_10_handles, *individual_and_mean_handles])
        assert individual_and_mean_handles[0].get_linewidth() == 0.5
        assert individual_and_mean_handles[1].get_marker() == "^"
        assert individual_and_mean_handles[1].get_linewidth() == 1.7
        assert list(individual_and_mean_handles[1].get_ydata()) == pytest.approx([0.4, 0.6])
        pd.testing.assert_frame_equal(scores_df, original_scores_df)
        pd.testing.assert_frame_equal(top_10_metros_df, original_top_10_df)
    finally:
        plt.close(figure)


@pytest.mark.parametrize("show_labels", [True, False])
def test_history_year_labels_can_be_customized_or_hidden(monkeypatch, show_labels):
    monkeypatch.setattr(plot_national_results, "HISTORY_X_TICK_LABELS", {1980: "'80", 2000: ""})
    monkeypatch.setattr(plot_national_results, "HISTORY_SHOW_X_TICK_LABELS", show_labels)
    scores_df = pd.DataFrame(
        {
            "study_area_id": ["cbsa_10000", "cbsa_10000"],
            "census_year": [1980, 2020],
            "geography_level": ["tracts", "tracts"],
            "metric": ["capy", "capy"],
            "value": [0.55, 0.95],
        }
    )
    top_10_metros_df = pd.DataFrame({"study_area_id": [], "name": []})
    figure, axes = plot_national_results.create_plot()

    try:
        plot_national_results.plot_score_history(
            axes, scores_df, top_10_metros_df, PipelineConfig()
        )
        figure.canvas.draw()

        expected_labels = ["'80", "1990", "", "2010", "2020"] if show_labels else []
        assert [label.get_text() for label in axes.get_xticklabels()] == expected_labels
        assert list(axes.get_xticks()) == [1980, 1990, 2000, 2010, 2020]
        assert all(line.get_visible() for line in axes.get_xgridlines())
    finally:
        plt.close(figure)


@pytest.mark.parametrize("grid_positions", [[0.6, 0.8, 2.0], []])
def test_history_grid_positions_preserve_ticks_limits_and_vertical_grid(
    monkeypatch, grid_positions
):
    monkeypatch.setitem(plot_national_results.HISTORY_Y_TICKS, MetricName.CAPY, [0.5, 0.75, 1.0])
    monkeypatch.setitem(plot_national_results.HISTORY_Y_GRID_LINES, MetricName.CAPY, grid_positions)
    monkeypatch.setattr(plot_national_results, "HISTORY_Y_GRID_COLOR", "#123456")
    monkeypatch.setattr(plot_national_results, "HISTORY_Y_GRID_LINEWIDTH", 1.2)
    scores_df = pd.DataFrame(
        {
            "study_area_id": ["cbsa_10000", "cbsa_10000"],
            "census_year": [1980, 2020],
            "geography_level": ["tracts", "tracts"],
            "metric": ["capy", "capy"],
            "value": [0.55, 0.95],
        }
    )
    top_10_metros_df = pd.DataFrame({"study_area_id": [], "name": []})
    figure, axes = plot_national_results.create_plot()

    try:
        axes.set_ylim(0.4, 1.1)
        plot_national_results.plot_score_history(
            axes, scores_df, top_10_metros_df, PipelineConfig()
        )
        figure.canvas.draw()

        assert list(axes.get_yticks()) == [0.5, 0.75, 1.0]
        assert axes.get_ylim() == (0.4, 1.1)
        assert axes.get_xlim() == (1978, 2022)
        assert not any(line.get_visible() for line in axes.get_ygridlines())
        assert all(line.get_visible() for line in axes.get_xgridlines())
        assert [list(line.get_ydata()) for line in axes.lines[2:]] == [
            [value, value] for value in grid_positions
        ]

        for line in axes.lines[2:]:
            assert line.get_color() == "#123456"
            assert line.get_linewidth() == 1.2
            assert line.get_zorder() < axes.lines[0].get_zorder()
    finally:
        plt.close(figure)


@pytest.mark.parametrize(
    "area_type,vintage,level,years,metrics",
    [
        (StudyAreaType.CBSA, 2010, GeographyLevel.TRACT, (2000, 2020), (MetricName.CAPY,)),
        (StudyAreaType.COUNTY, 1990, GeographyLevel.TRACT, (1990,), (MetricName.DISSIMILARITY,)),
        (
            StudyAreaType.MAX_CITY,
            2020,
            GeographyLevel.BLOCK_GROUP,
            (1980, 1990, 2020),
            (MetricName.CAPY, MetricName.MORAN_ROW_STANDARDIZED),
        ),
        (StudyAreaType.CBSA, 2020, GeographyLevel.BLOCK, (1990, 2020), (MetricName.CAPY,)),
    ],
)
@pytest.mark.parametrize("include_unplotted_selections", [False, True])
def test_configured_histories_read_saved_scores_and_render_selected_years(
    tmp_path, monkeypatch, area_type, vintage, level, years, metrics, include_unplotted_selections
):
    config = PipelineConfig(
        study_area_type=area_type,
        study_area_vintage=vintage,
        census_geography_levels=(level,),
        census_geography_years=years,
        population_comparisons=(PopulationComparison.WHITE_BLACK,),
        metric_names=metrics,
    )
    area_folder = f"{area_type}/{vintage}"
    definitions_directory = tmp_path / config.study_area_directory / area_folder
    definitions_directory.mkdir(parents=True)
    definitions_df = gpd.GeoDataFrame(
        {"study_area_id": ["area_1"], "name": ["Example"], "definition_population": [200000]},
        geometry=[Point(0, 0)],
        crs="EPSG:4326",
    )
    definitions_df.to_parquet(definitions_directory / "definitions.parquet")
    metric_directory = tmp_path / config.metric_results_directory / area_type
    study_area_label = f"{area_type.upper()}{vintage % 100:02d}"
    metric_directory.mkdir(parents=True)
    expected_years = [year for year in years if year != 1980 or level == GeographyLevel.TRACT]
    graph_summary_rows = []

    for year in expected_years:
        identity = {"study_area_id": "area_1", "census_year": year, "geography_level": level}
        graph_summary_rows.append(identity)
        pd.DataFrame(
            [
                {
                    **identity,
                    "population_comparison": "white_black",
                    "metric": metric,
                    "value": 0.6,
                }
                for metric in metrics
            ]
        ).to_parquet(metric_directory / f"{year}_{level}_{study_area_label}_metrics.parquet")

    # A broader saved run must not force an unrequested year into the figure selection.
    pd.DataFrame([*graph_summary_rows, {**graph_summary_rows[-1], "census_year": 2010}]).to_parquet(
        metric_directory / f"{study_area_label}_graph_summary.parquet"
    )
    if include_unplotted_selections:
        # County metric files are not used by these image sets.
        config.census_geography_levels = (GeographyLevel.COUNTY, level)

    prepared_directory = tmp_path / "prepared"
    prepare_national_results.prepare_national_figure_data(config, tmp_path, prepared_directory)
    histories_df = pd.read_parquet(prepared_directory / "trajectory_rows.parquet")
    assert set(histories_df.census_year) == set(expected_years)
    assert set(histories_df.metric) == set(metrics)
    assert set(histories_df.population_comparison) == {"white_black"}
    exports = []

    def check_export(figure, output_path):
        axes = figure.axes[0]
        assert list(axes.get_xticks()) == sorted(years)
        assert axes.get_xlim() == (min(years) - 2, max(years) + 2)
        assert len(axes.patches) == int(1980 in years and level != GeographyLevel.TRACT)
        plotted_metrics = [
            metric for metric in prepare_national_results.HISTORY_METRICS if metric in metrics
        ]
        metric = plotted_metrics[len(exports)]
        assert len(axes.lines) == 3 + len(plot_national_results.HISTORY_Y_GRID_LINES[metric])
        exports.append(output_path)
        plt.close(figure)

    monkeypatch.setattr(plot_national_results, "save_plot", check_export)
    monkeypatch.setattr(plot_national_results, "save_legend", lambda *_: None)
    plot_national_results.plot_national_figures(config, tmp_path / "figures", prepared_directory)
    assert len(exports) == len(metrics)

    # Missing supported years must fail rather than silently shorten the cohort.
    (metric_directory / f"{expected_years[0]}_{level}_{study_area_label}_metrics.parquet").unlink()
    with pytest.raises(FileNotFoundError):
        prepare_national_results.prepare_national_figure_data(config, tmp_path, prepared_directory)


@pytest.mark.parametrize(
    "vintage,years,excluded",
    [(2020, (1980, 1990), True), (2020, (1990, 2020), False), (2010, (1980, 1990), False)],
)
def test_two_node_exclusions_only_apply_to_1980_histories_of_2020_cbsas(vintage, years, excluded):
    config = PipelineConfig(
        population_comparisons=(PopulationComparison.WHITE_BLACK,),
        study_area_type=StudyAreaType.CBSA,
        study_area_vintage=vintage,
        census_geography_levels=(GeographyLevel.TRACT,),
        census_geography_years=years,
        metric_names=(MetricName.CAPY,),
    )
    definitions_df = pd.DataFrame({"study_area_id": ["cbsa_25940", "cbsa_10000"]})
    scores_df = pd.DataFrame(
        [
            {
                "study_area_id": area_id,
                "census_year": year,
                "geography_level": "tracts",
                "population_comparison": "white_black",
                "metric": "capy",
                "value": 0.6,
            }
            for area_id in definitions_df.study_area_id
            for year in years
        ]
    )
    original_scores_df = scores_df.copy(deep=True)
    histories_df = prepare_national_results.select_score_histories(
        scores_df,
        prepare_national_results.select_history_years(config),
        (MetricName.CAPY,),
        config,
    )
    assert ("cbsa_25940" not in set(histories_df.study_area_id)) == excluded
    assert "cbsa_10000" in set(histories_df.study_area_id)
    pd.testing.assert_frame_equal(scores_df, original_scores_df)


def test_missing_requested_moran_rows_are_rejected_even_when_capy_is_complete():
    history_selections_df = pd.DataFrame(
        [{"population_comparison": "white_black", "geography_level": "tracts"}]
    )
    graph_summary_df = pd.DataFrame(
        [{"study_area_id": "cbsa_10000", "census_year": 2020, "geography_level": "tracts"}]
    )
    scores_df = graph_summary_df.assign(
        population_comparison="white_black", metric="capy", value=0.6
    )

    with pytest.raises(ValueError, match="run compute-metrics"):
        prepare_national_results.check_figure_score_selection(
            scores_df,
            graph_summary_df,
            history_selections_df,
            (MetricName.CAPY, MetricName.MORAN_ROW_STANDARDIZED),
        )


@pytest.mark.parametrize(
    "metric",
    [
        metric
        for metric in prepare_national_results.HISTORY_METRICS
        if metric not in prepare_national_results.PRIMARY_METRICS
    ],
)
def test_additional_histories_keep_population_exclusions_and_independent_cohorts(
    tmp_path, monkeypatch, metric
):
    config = PipelineConfig(
        study_area_type=StudyAreaType.CBSA,
        census_geography_years=(1980, 2020),
        census_geography_levels=(GeographyLevel.TRACT,),
        population_comparisons=(PopulationComparison.WHITE_BLACK,),
        metric_names=(MetricName.CAPY, metric),
    )
    definitions_df = pd.DataFrame(
        {
            "study_area_id": ["cbsa_10000", "cbsa_10001", "cbsa_10002", "cbsa_25940"],
            "definition_population": [300000, 200000, 100000, 150000],
        }
    )
    scores_df = pd.DataFrame(
        [
            {
                "study_area_id": area_id,
                "census_year": year,
                "geography_level": "tracts",
                "population_comparison": "white_black",
                "metric": score,
                "value": float("nan")
                if (area_id, year, score) == ("cbsa_10000", 1980, metric)
                else 0.6,
            }
            for area_id in definitions_df.study_area_id
            for year in config.census_geography_years
            for score in config.metric_names
        ]
    )
    graph_summary_df = scores_df[prepare_national_results.IDENTITY_COLUMNS].drop_duplicates()
    monkeypatch.setattr(
        prepare_national_results,
        "read_national_figure_inputs",
        lambda *_: (scores_df, definitions_df, graph_summary_df),
    )
    prepare_national_results.prepare_national_figure_data(config, tmp_path, tmp_path)
    histories_df = pd.read_parquet(tmp_path / "trajectory_rows.parquet")

    assert set(histories_df.loc[histories_df.metric.eq(MetricName.CAPY), "study_area_id"]) == {
        "cbsa_10000",
        "cbsa_10001",
    }
    assert set(histories_df.loc[histories_df.metric.eq(metric), "study_area_id"]) == {"cbsa_10001"}
    assert set(histories_df.census_year) == {1980, 2020}
