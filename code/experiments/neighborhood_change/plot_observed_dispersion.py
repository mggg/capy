"""Render individual observed dispersion components from saved results."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Circle
from national_pipeline.population_table_columns import GeographyColumn
from plotting.figure_style import DENIM, create_plot, save_legend, save_plot, write_figure_png

from experiments.neighborhood_change.observed_dispersion import fill_cluster_holes

BLACK_SHARE_CMAP = LinearSegmentedColormap.from_list(
    "black_share",
    [
        "#d6e8ff",
        "#c2dcfe",
        "#aaccfd",
        "#90bbfb",
        "#76a9f7",
        "#5e97f0",
        "#4685e6",
        "#3374d9",
        "#2567cc",
        "#1d62c2",
        "#1a61be",
        "#1560bd",
    ],
)


CENTER_EDGE_COLOR = "black"
ACCENT_COLOR = "#ED5113"
RADIAL_BACKGROUND_COLOR = "#fcfcfb"
OUTLINE_COLOR = "#c3c2b7"
DISTANCE_RING_COLOR = "#dddddd"

TRACT_EDGE_COLOR = "grey"

MORAN_Y_LIMITS = (0.65, 0.90)
MORAN_Y_TICKS = (0.7, 0.8, 0.9)
CAPY_Y_LIMITS = (0.65, 0.90)
CAPY_Y_TICKS = (0.7, 0.8, 0.9)


def plot_observed_dispersion(data_directory: Path, output_directory: Path) -> None:
    """Render saved neighborhood histories, with choropleths and score traces for Chicago.

    Args:
        data_directory (Path): Folder with complete cluster_maps and cluster_scores
            Parquets and cluster_memberships from one run. The saved map buffer determines traces.
        output_directory (Path): Destination for separate PNG plots and two Black-share colorbars.

    Raises:
        OSError: Saved inputs cannot be read or a figure cannot be written.
        KeyError: A required column is absent.
        ValueError: Map rows do not identify exactly one plotting buffer.
    """
    maps_df = gpd.read_parquet(data_directory / "cluster_maps.parquet")
    memberships_df = pd.read_parquet(data_directory / "cluster_memberships.parquet")
    scores_df = pd.read_parquet(data_directory / "cluster_scores.parquet")
    (map_buffer_steps,) = maps_df.buffer_steps.unique()
    core_memberships_df = memberships_df.loc[memberships_df.buffer_steps.eq(0)]
    map_buffer_scores_df = scores_df.loc[scores_df.buffer_steps.eq(map_buffer_steps)]

    for cluster_id, neighborhood_maps_df in maps_df.groupby("cluster"):
        neighborhood_memberships_df = core_memberships_df.loc[
            core_memberships_df.cluster.eq(cluster_id)
        ]
        neighborhood_scores_df = map_buffer_scores_df.loc[
            map_buffer_scores_df.cluster.eq(cluster_id)
        ].sort_values("year")
        plot_neighborhood_history(
            str(cluster_id),
            gpd.GeoDataFrame(neighborhood_maps_df, crs=maps_df.crs),
            neighborhood_memberships_df,
            neighborhood_scores_df,
            output_directory / str(cluster_id),
        )

    for name, minimum in (("choro", 0.3), ("radial", 0)):
        figure, axes = create_plot()
        figure.set_size_inches(0.5, 3.4)
        figure.colorbar(ScalarMappable(norm=Normalize(minimum, 1), cmap=BLACK_SHARE_CMAP), cax=axes)
        axes.set_box_aspect(22)
        save_plot(figure, output_directory / f"{name}_black_share_colorbar")


def plot_neighborhood_history(
    cluster_id: str,
    maps_df: gpd.GeoDataFrame,
    core_memberships_df: pd.DataFrame,
    scores_df: pd.DataFrame,
    output_directory: Path,
) -> None:
    """Save yearly radial views and, for Chicago neighborhoods, choropleths and score traces.

    Args:
        cluster_id (str): Saved city/neighborhood identifier; Chicago IDs start with chicago_.
        maps_df (gpd.GeoDataFrame): One neighborhood's tract geometry and radial coordinates
            across census years, all at the same graph buffer.
        core_memberships_df (pd.DataFrame): That neighborhood's buffer-zero tract IDs by year.
        scores_df (pd.DataFrame): Year-sorted scores at the buffer used by maps_df.
        output_directory (Path): Destination for this neighborhood's PNG plots.

    Raises:
        KeyError: A required saved column is absent.
        OSError: A PNG cannot be written.
    """
    map_bounds = maps_df.total_bounds
    radial_limit = np.hypot(maps_df.radial_x, maps_df.radial_y).max() + 1
    is_chicago_neighborhood = cluster_id.startswith("chicago_")

    for year, year_rows_df in maps_df.groupby("year"):
        year_map_df = gpd.GeoDataFrame(year_rows_df, crs=maps_df.crs)

        if is_chicago_neighborhood:
            core_tract_ids = core_memberships_df.loc[
                core_memberships_df.year.eq(year), "geographic_id"
            ]
            figure, axes = create_plot()
            plot_neighborhood_map(axes, year_map_df, core_tract_ids, map_bounds)

            save_plot(figure, output_directory / f"choro_{year}_black_share")

        figure, axes = create_plot()
        plot_radial_black_share(axes, year_map_df, radial_limit)

        save_plot(figure, output_directory / f"radial_{year}_black_share")

    if is_chicago_neighborhood:
        figure, moran_axes = create_plot()
        figure.set_size_inches(10, 1.5)
        capy_axes = moran_axes.twinx()
        plot_neighborhood_scores(moran_axes, capy_axes, scores_df)
        moran_axes.set(ylim=MORAN_Y_LIMITS, yticks=MORAN_Y_TICKS)
        capy_axes.set(ylim=CAPY_Y_LIMITS, yticks=CAPY_Y_TICKS)

        write_figure_png(figure, output_directory / "metrics_over_time")
        save_legend(
            [*moran_axes.lines, *capy_axes.lines], output_directory / "metrics_over_time_legend"
        )


def plot_neighborhood_map(
    axes: Axes,
    tracts_df: gpd.GeoDataFrame,
    core_tract_ids: pd.Series,
    bounds: np.ndarray,
) -> None:
    """Draw one year's Black-share map with its selected core outline and medoid.

    Args:
        axes (Axes): Caller-owned axes to draw on; left open for further adjustments.
        tracts_df (gpd.GeoDataFrame): One neighborhood/year's selected plotting-buffer tracts.
        core_tract_ids (pd.Series): Geographic IDs belonging to that year's buffer-zero core.
        bounds (np.ndarray): Shared neighborhood extent in min-x, min-y, max-x, max-y order.
    """
    tracts_df.plot(
        ax=axes,
        column="black_share",
        cmap=BLACK_SHARE_CMAP,
        vmin=0.3,
        vmax=1,
        edgecolor=TRACT_EDGE_COLOR,
        linewidth=0.4,
    )
    core_shape = fill_cluster_holes(
        tracts_df.loc[tracts_df[GeographyColumn.GEOGRAPHIC_ID].isin(core_tract_ids)].geometry
    )
    gpd.GeoSeries([core_shape], crs=tracts_df.crs).boundary.plot(
        ax=axes, color=CENTER_EDGE_COLOR, linewidth=1.2
    )
    medoid_centroid = tracts_df.loc[tracts_df.is_medoid].geometry.centroid
    axes.scatter(
        medoid_centroid.x,
        medoid_centroid.y,
        marker="*",
        color=ACCENT_COLOR,
        edgecolor=CENTER_EDGE_COLOR,
        linewidth=0.4,
        s=60,
    )
    axes.set(xlim=(bounds[0], bounds[2]), ylim=(bounds[1], bounds[3]))
    axes.set_axis_off()


def plot_radial_black_share(axes: Axes, tracts_df: gpd.GeoDataFrame, limit: float) -> None:
    """Place tracts by full-city graph distance and projected centroid angle, without text.

    Args:
        axes (Axes): Caller-owned axes to draw on; left open for further adjustments.
        tracts_df (gpd.GeoDataFrame): Saved radial_x, radial_y, and black_share for one year.
        limit (float): Positive symmetric extent shared across that cluster's years.
    """
    axes.set_facecolor(RADIAL_BACKGROUND_COLOR)

    for radius in range(1, int(limit)):
        axes.add_patch(
            Circle((0, 0), radius, fill=False, edgecolor=DISTANCE_RING_COLOR, linewidth=0.6)
        )

    maximum_graph_distance = np.hypot(tracts_df.radial_x, tracts_df.radial_y).max()
    axes.add_patch(
        Circle(
            (0, 0),
            maximum_graph_distance,
            fill=False,
            edgecolor=OUTLINE_COLOR,
            linewidth=1.1,
            linestyle="--",
        )
    )

    axes.scatter(
        tracts_df.radial_x,
        tracts_df.radial_y,
        c=tracts_df.black_share,
        cmap=BLACK_SHARE_CMAP,
        vmin=0,
        vmax=1,
        s=20,
        edgecolor=RADIAL_BACKGROUND_COLOR,
        linewidth=0.2,
    )
    axes.scatter(
        [0], [0], marker="*", color=ACCENT_COLOR, edgecolor=CENTER_EDGE_COLOR, linewidth=0.4, s=60
    )
    axes.set(xlim=(-limit, limit), ylim=(-limit, limit), aspect="equal")
    axes.set_axis_off()


def plot_neighborhood_scores(moran_axes: Axes, capy_axes: Axes, scores_df: pd.DataFrame) -> None:
    """Draw Moran and Capy traces with colored ticks; the caller sets their y-axis ranges.

    Args:
        moran_axes (Axes): Caller-owned axes for Moran scores and year ticks.
        capy_axes (Axes): Caller-owned twin axes for Capy scores, sharing the year axis.
        scores_df (pd.DataFrame): One neighborhood's year-sorted scores at its plotted buffer.
    """
    for tick_label in capy_axes.get_yticklabels():
        tick_label.set_fontfamily("serif")

    for axes, metric, color, label in (
        (moran_axes, "moran_row_standardized", DENIM, "Moran’s I"),
        (capy_axes, "capy", ACCENT_COLOR, "Capy"),
    ):
        axes.plot(
            scores_df.year,
            scores_df[metric],
            "o-",
            color=color,
            markersize=4,
            linewidth=1.2,
            label=label,
        )
        axes.tick_params(axis="y", length=0, colors=color)
        axes.grid(False)
        axes.spines[:].set_visible(True)
        axes.spines[:].set_color(OUTLINE_COLOR)

    moran_axes.set_xticks(scores_df.year)
    moran_axes.set_xlim(scores_df.year.min() - 3, scores_df.year.max() + 3)
