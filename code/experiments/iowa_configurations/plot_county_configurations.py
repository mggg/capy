"""Draw Iowa county arrangements and their score distributions from saved results."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from matplotlib.patches import Patch
from national_pipeline.compute_metrics.metric_types import MetricName
from national_pipeline.population_table_columns import GeographyColumn, PopulationColumn
from plotting.figure_style import (
    CADMIUM_GREEN,
    DARK_TANGERINE,
    DENIM,
    PURPLE_HEART,
    SLATE_GRAY,
    create_plot,
    save_legend,
    save_plot,
)

from experiments.iowa_configurations.county_configurations import CountyArrangement

COMPARISON_COLORS = {
    CountyArrangement.RANDOM: DENIM,
    CountyArrangement.CLUSTERED: DARK_TANGERINE,
    CountyArrangement.ISOLATED: CADMIUM_GREEN,
}
ARRANGEMENT_COLORS = COMPARISON_COLORS | {CountyArrangement.MULTICLUSTER: PURPLE_HEART}


def plot_iowa_experiments(data_directory: Path, output_directory: Path) -> None:
    """Render county maps, individual score scatters, and three-arrangement comparisons.

    Args:
        data_directory (Path): Folder containing matching iowa_scores, iowa_examples, and
            iowa_edges Parquets. Failed attempts with null scores contribute no plotted points.
        output_directory (Path): Destination for individual PNG maps and scatter panels,
            combined random/clustered/isolated panels, and their separate legend.

    Raises:
        OSError: A saved table cannot be read or a figure cannot be written.
        KeyError: A required result column is absent.
        ValueError: A required arrangement or finite population share is absent.
    """
    scores_df = pd.read_parquet(data_directory / "iowa_scores.parquet")
    examples_df = gpd.read_parquet(data_directory / "iowa_examples.parquet")
    edges_df = pd.read_parquet(data_directory / "iowa_edges.parquet")

    if (
        not scores_df.arrangement.eq(CountyArrangement.RANDOM).any()
        or not examples_df.arrangement.eq(CountyArrangement.RANDOM).any()
    ):
        raise ValueError("Missing Iowa random baseline; rerun code/run_experiment.py iowa")

    for arrangement in CountyArrangement:
        counties_df = examples_df.loc[examples_df.arrangement.eq(arrangement)]
        figure, axes = create_plot()
        plot_county_population_graph(axes, counties_df, edges_df)

        save_plot(figure, output_directory / arrangement / f"dualgraph_ia_county_{arrangement}")
        selected_scores_df = scores_df.loc[scores_df.arrangement.eq(arrangement)]

        for metric in (MetricName.CAPY, MetricName.MORAN_ROW_STANDARDIZED):
            figure, axes = create_plot()
            plot_county_score_by_population_share(axes, selected_scores_df, metric)
            axes.set_ylim((0, 1) if metric == MetricName.CAPY else (-1, 1))

            save_plot(
                figure,
                output_directory / arrangement / f"{metric}_by_share_ia_county_{arrangement}",
            )

    for metric in (MetricName.CAPY, MetricName.MORAN_ROW_STANDARDIZED):
        figure, axes = create_plot()
        plot_county_arrangement_comparison(axes, scores_df, metric)
        axes.set_ylim((0, 1) if metric == MetricName.CAPY else (-1, 1))
        save_plot(figure, output_directory / f"{metric}_by_share_ia_county_comparison")

    save_legend(
        [
            Patch(color=color, label=arrangement.value.capitalize())
            for arrangement, color in COMPARISON_COLORS.items()
        ],
        output_directory / "county_arrangement_legend",
    )


def plot_county_population_graph(
    axes: Axes, counties_df: gpd.GeoDataFrame, edges_df: pd.DataFrame
) -> None:
    """Draw a county arrangement using the adjacency saved with its computed scores.

    Args:
        axes (Axes): Caller-owned axes, left open for adjustments and export.
        counties_df (gpd.GeoDataFrame): County polygons, geographic IDs, total populations,
            and first_group assignments for one arrangement.
        edges_df (pd.DataFrame): Saved undirected source/target geographic ID pairs.

    Raises:
        KeyError: A required column or an edge endpoint is absent from the county table.
    """
    county_centroids = counties_df.geometry.centroid
    county_positions = np.column_stack([county_centroids.x, county_centroids.y])
    positions_by_county = dict(
        zip(counties_df[GeographyColumn.GEOGRAPHIC_ID], county_positions, strict=True)
    )
    edge_segments = [
        [positions_by_county[source], positions_by_county[target]]
        for source, target in edges_df[["source", "target"]].itertuples(index=False, name=None)
    ]
    axes.add_collection(LineCollection(edge_segments, colors=SLATE_GRAY, linewidths=0.4, zorder=0))
    axes.scatter(
        county_positions[:, 0],
        county_positions[:, 1],
        c=np.where(counties_df.first_group, DARK_TANGERINE, DENIM),
        s=counties_df[PopulationColumn.TOTAL].to_numpy() / 4000,
        edgecolors="none",
        linewidths=0,
    )
    axes.set_aspect("equal")
    axes.set_axis_off()


def plot_county_score_by_population_share(
    axes: Axes, scores_df: pd.DataFrame, metric: MetricName
) -> None:
    """Draw one arrangement's scores against achieved first-group population share.

    Args:
        axes (Axes): Caller-owned axes, left open for adjustments and export.
        scores_df (pd.DataFrame): Saved scores, group_share, and arrangement for one family.
            Failed attempts with null scores contribute no plotted points.
        metric (MetricName): CAPY or MORAN_ROW_STANDARDIZED score to draw.

    Raises:
        ValueError: No finite population share exists.
        KeyError: A required score or population-share column is absent.
    """
    set_county_population_share_axes(axes, scores_df)
    axes.scatter(
        scores_df.group_share,
        scores_df[metric],
        c=scores_df.arrangement.map(ARRANGEMENT_COLORS).tolist(),
        s=0.1,
        linewidths=0,
        edgecolors="none",
        alpha=1,
        rasterized=True,
    )


def plot_county_arrangement_comparison(
    axes: Axes, scores_df: pd.DataFrame, metric: MetricName
) -> None:
    """Compare random, clustered, and isolated counties with reproducible point layering.

    Args:
        axes (Axes): Caller-owned axes, left open for adjustments and export.
        scores_df (pd.DataFrame): Saved scores containing all three comparison arrangements.
            Multicluster rows are excluded. The input table is unchanged.
        metric (MetricName): CAPY or MORAN_ROW_STANDARDIZED score to draw.

    Raises:
        ValueError: A comparison arrangement is absent or no finite population share exists.
        KeyError: A required score, arrangement, or population-share column is absent.
    """
    missing_arrangements = set(COMPARISON_COLORS) - set(scores_df.arrangement)

    if missing_arrangements:
        raise ValueError("Missing Iowa comparison arrangements; rerun code/run_experiment.py iowa")

    comparison_df = scores_df.loc[scores_df.arrangement.isin(COMPARISON_COLORS)].sample(
        frac=1, random_state=42
    )
    set_county_population_share_axes(axes, comparison_df)
    axes.scatter(
        comparison_df.group_share,
        comparison_df[metric],
        c=comparison_df.arrangement.map(COMPARISON_COLORS).tolist(),
        s=0.2,
        linewidths=0,
        edgecolors="none",
        alpha=1,
        rasterized=True,
    )


def set_county_population_share_axes(axes: Axes, scores_df: pd.DataFrame) -> None:
    """Set shared Iowa scatter styling and bounds; reject absent finite population shares."""
    maximum_share = np.ceil(scores_df.group_share.max() * 10) / 10

    if not np.isfinite(maximum_share):
        raise ValueError("No achieved population shares are available for the Iowa plot")

    axes.set_xlim(0, maximum_share)
    axes.grid(False)
    axes.spines[:].set_visible(True)
    axes.spines[:].set_color(SLATE_GRAY)
    axes.set_xticks(np.arange(0, maximum_share + 0.05, 0.1))
