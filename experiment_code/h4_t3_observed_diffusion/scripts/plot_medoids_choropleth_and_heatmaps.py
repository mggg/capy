import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
import pandas as pd
import geopandas as gpd
from pathlib import Path


EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
GEO_DIR = EXPERIMENT_DIR.parent.parent / "data" / "processed" / "clipped_geographies"

METRICS = [("moran", "Moran's I"), ("dissimilarity", "Dissimilarity"),
           ("half_edge", "Half Edge (capy)"), ("spread", "Spread")] #maybe add mass later?
norm = mcolors.Normalize(vmin=0, vmax=1)
cmap = plt.cm.Blues

tracts = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_tracts.csv", dtype={'area_code': str, 'gisjoin': str})
tracts['black_share'] = tracts['black_population'] / (tracts['black_population'] + tracts['white_population'])

metrics = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_metrics.csv", dtype={'area_code': str, 'center_gisjoin': str})

for (area_code, city_name, cluster), tract_selections in tracts.groupby(['area_code', 'city_name', 'cluster'], sort=True):
    print(f"Plotting {city_name}, {cluster}")
    tracts_buf10 = tract_selections[tract_selections['buffer_size'] == 10]
    cluster_metrics = metrics[(metrics['area_code'] == area_code) & (metrics['cluster'] == cluster)]
    years = sorted(cluster_metrics['year'].unique())

    # layout: choropleth (top) + heatmaps (bottom)
    fig = plt.figure(figsize=(20, 11))
    outer_gs = gridspec.GridSpec(2, 1, height_ratios=[3, 2], figure=fig, hspace=0.4)
    top_gs = gridspec.GridSpecFromSubplotSpec(1, len(years), subplot_spec=outer_gs[0], wspace=0.05)
    bot_gs = gridspec.GridSpecFromSubplotSpec(1, len(METRICS), subplot_spec=outer_gs[1], wspace=0.5)
    axes = [fig.add_subplot(top_gs[0, i]) for i in range(len(years))]
    heat_axes = [fig.add_subplot(bot_gs[0, i]) for i in range(len(METRICS))]

    # fig.text(0.5, 0.95, "note here", ha='center', fontsize=10, style='italic')

    # choropleth: all buffer=10 tracts colored by black_share
    for ax, year in zip(axes, years):
        year_selections = tracts_buf10[tracts_buf10['year'] == year]
        medoid_gisjoin = cluster_metrics[(cluster_metrics['year'] == year) & (cluster_metrics['buffer_size'] == 0)].iloc[0]['center_gisjoin']

        geo_path = GEO_DIR / str(year) / f'tracts_in_max_city_{area_code}_{year}_march_2020_vintage.gpkg'
        gdf = gpd.read_file(geo_path)

        cluster_gdf = gdf.merge(year_selections[['gisjoin', 'black_share']], left_on='GISJOIN', right_on='gisjoin', how='inner')
        cluster_gdf['choropleth_color'] = cluster_gdf['black_share'].apply(lambda x: cmap(norm(x)))
        cluster_gdf.plot(ax=ax, color=cluster_gdf['choropleth_color'].tolist(), edgecolor='grey', linewidth=0.2)

        buf0_tracts = tract_selections[(tract_selections['year'] == year) & (tract_selections['buffer_size'] == 0)]
        buf0_gdf = gdf.merge(buf0_tracts[['gisjoin']], left_on='GISJOIN', right_on='gisjoin', how='inner')
        gpd.GeoSeries([buf0_gdf.geometry.union_all()], crs=gdf.crs).boundary.plot(
            ax=ax, color='black', linewidth=1.5, zorder=4)

        medoid_geom = gdf.loc[gdf['GISJOIN'] == medoid_gisjoin, 'geometry']
        if not medoid_geom.empty:
            c = medoid_geom.iloc[0].centroid
            ax.scatter(c.x, c.y, marker='*', s=50, color='tomato', edgecolor='black', linewidth=0.5, zorder=5)

        ax.set_title(str(year))
        ax.set_aspect('equal')
        ax.axis('off')

    color_scale = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    fig.colorbar(color_scale, ax=axes, label="Black population share", fraction=0.025, pad=0.02)

    # heatmaps (all buffer sizes × all years)
    all_buffer_sizes = sorted(cluster_metrics['buffer_size'].unique())
    for ax_h, (col, label) in zip(heat_axes, METRICS):
        pivot = cluster_metrics.pivot(index='buffer_size', columns='year', values=col).sort_index()
        im = ax_h.pcolormesh(range(len(years)), range(len(all_buffer_sizes)), pivot.values, cmap='Blues', shading='nearest')
        ax_h.invert_yaxis()
        ax_h.set_xticks(range(len(years)))
        ax_h.set_xticklabels([str(y) for y in years], fontsize=8, rotation=45, ha='right')
        ax_h.set_yticks(range(len(all_buffer_sizes)))
        ax_h.set_yticklabels(all_buffer_sizes, fontsize=7)
        ax_h.set_title(label, fontsize=10)
        if ax_h is heat_axes[0]:
            ax_h.set_ylabel("Buffer size", fontsize=9)
        fig.colorbar(im, ax=ax_h, fraction=0.06, pad=0.04)

    fig.legend(handles=[Line2D([0], [0], color='tomato', marker='*', markersize=12, linestyle='None', label='Medoid (at buffer = 0)')], loc='upper left', bbox_to_anchor=(0.45, 0.95), fontsize=9, frameon=False)
    fig.legend(handles=[Line2D([0], [0], color='black', markersize=12, linestyle='-', label='Outline of the original cluster')], loc='upper left', bbox_to_anchor=(0.45, 0.93), fontsize=9, frameon=False)
    # fig.text(0.01, 0.93, "your annotation here", ha='left', fontsize=9, color='dimgrey')
    fig.suptitle(f'{city_name} — {cluster}', fontsize=14)

    figure_path = EXPERIMENT_DIR / "figures" / "metrics_heatmap_by_buffers" / f"{city_name}_{cluster}_choropleth_and_metrics.png"
    figure_path.parent.mkdir(exist_ok=True)
    fig.savefig(figure_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved {figure_path}")
