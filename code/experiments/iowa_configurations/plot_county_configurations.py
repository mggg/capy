"""Draw Iowa county arrangements and their score distributions from saved results."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from national_pipeline.compute_metrics.metric_types import MetricName
from national_pipeline.population_table_columns import GeographyColumn, PopulationColumn
from plotting.figure_style import DARK_TANGERINE, DENIM, create_plot, save_plot

from experiments.iowa_configurations.county_configurations import CountyArrangement

NODE_EDGE_COLOR = "black"
AXIS_COLOR = "#bbbbbb"
COUNTY_EDGE_COLOR = "#777777"
SECOND_GROUP_COLOR = "#2267BC"


def plot_iowa_experiments(data_directory: Path, output_directory: Path) -> None:
    """Render population-sized county adjacency nodes and score-versus-achieved-share scatters.

    Args:
        data_directory (Path): Folder containing matching iowa_scores, iowa_examples, and
            iowa_edges Parquets. Failed attempts with null scores contribute no plotted points.
        output_directory (Path): Destination for individual PNG maps and scatter panels.

    Raises:
        OSError: A saved table cannot be read or a figure cannot be written.
        KeyError: A required result column is absent.
    """
    scores_df = pd.read_parquet(data_directory / "iowa_scores.parquet")
    examples_df = gpd.read_parquet(data_directory / "iowa_examples.parquet")
    edges_df = pd.read_parquet(data_directory / "iowa_edges.parquet")

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
    axes.add_collection(
        LineCollection(edge_segments, colors=COUNTY_EDGE_COLOR, linewidths=0.4, zorder=0)
    )
    axes.scatter(
        county_positions[:, 0],
        county_positions[:, 1],
        c=np.where(counties_df.first_group, DARK_TANGERINE, SECOND_GROUP_COLOR),
        s=counties_df[PopulationColumn.TOTAL].to_numpy() / 4000,
        edgecolors=NODE_EDGE_COLOR,
        linewidths=0.3,
    )
    axes.set_aspect("equal")
    axes.set_axis_off()


def plot_county_score_by_population_share(
    axes: Axes, scores_df: pd.DataFrame, metric: MetricName
) -> None:
    """Draw one arrangement's scores against achieved first-group population share.

    Args:
        axes (Axes): Caller-owned axes, left open for adjustments and export.
        scores_df (pd.DataFrame): Saved scores and group_share for one arrangement.
            Failed attempts with null scores contribute no plotted points.
        metric (MetricName): CAPY or MORAN_ROW_STANDARDIZED score to draw.

    Raises:
        ValueError: No finite population share exists.
        KeyError: A required score or population-share column is absent.
    """
    maximum_share = np.ceil(scores_df.group_share.max() * 10) / 10

    if not np.isfinite(maximum_share):
        raise ValueError("No achieved population shares are available for the Iowa plot")

    axes.scatter(
        scores_df.group_share,
        scores_df[metric],
        color=DENIM,
        s=0.1,
        alpha=1,
        rasterized=True,
    )
    axes.set_xlim(0, maximum_share)
    axes.grid(False)
    axes.spines[:].set_visible(True)
    axes.spines[:].set_color(AXIS_COLOR)
    axes.set_xticks(np.arange(0, maximum_share + 0.05, 0.1))
