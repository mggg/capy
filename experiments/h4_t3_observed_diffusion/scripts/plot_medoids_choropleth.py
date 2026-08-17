# Choropleth plots of clusters at selected buffer sizes.
# Layout: rows = buffer sizes, columns = years.

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
import pandas as pd
import geopandas as gpd
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
GEO_DIR = EXPERIMENT_DIR.parent.parent / "data" / "processed" / "clipped_geographies"

SHOW_BUFFERS = [0, 1, 2, 5, 10]

norm = mcolors.Normalize(vmin=0, vmax=1)
cmap = plt.cm.Blues

all_selections = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_tracts.csv", dtype={'area_code': str, 'gisjoin': str})
all_selections['black_share'] = all_selections['black_population'] / (all_selections['black_population'] + all_selections['white_population'])
all_metrics = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_metrics.csv", dtype={'area_code': str, 'center_gisjoin': str})


for (area_code, city_name, cluster), cluster_selections in all_selections.groupby(['area_code', 'city_name', 'cluster'], sort=True):
    print(f"Plotting {city_name}, {cluster}")
    cluster_metrics = all_metrics[(all_metrics['area_code'] == area_code) & (all_metrics['cluster'] == cluster)]
    years = sorted(cluster_metrics['year'].unique())

    fig, axes = plt.subplots(len(SHOW_BUFFERS), len(years), figsize=(20, 5 * len(SHOW_BUFFERS)))

    # cache GDFs so each year's file is read once, not once per buffer row
    gdf_cache = {}
    for year in years:
        geo_path = GEO_DIR / str(year) / f'tracts_in_max_city_{area_code}_{year}_march_2020_vintage.gpkg'
        gdf_cache[year] = gpd.read_file(geo_path)

    # shared axis limits per year column — derived from the largest buffer so all rows align
    year_limits = {}
    max_buf = max(SHOW_BUFFERS)
    for year in years:
        gdf = gdf_cache[year]
        largest = cluster_selections[(cluster_selections['year'] == year) &
                                     (cluster_selections['buffer_size'] == max_buf)]
        largest_gdf = gdf.merge(largest[['gisjoin']], left_on='GISJOIN', right_on='gisjoin', how='inner')
        if not largest_gdf.empty:
            minx, miny, maxx, maxy = largest_gdf.total_bounds
            pad = max(maxx - minx, maxy - miny) * 0.01
            year_limits[year] = (minx - pad, maxx + pad, miny - pad, maxy + pad)

    for row_i, buf in enumerate(SHOW_BUFFERS):
        buf_selections = cluster_selections[cluster_selections['buffer_size'] == buf]

        for col_i, year in enumerate(years):
            ax = axes[row_i, col_i]
            gdf = gdf_cache[year]

            # tracts for this buffer + year
            year_buf = buf_selections[buf_selections['year'] == year]
            cluster_gdf = gdf.merge(year_buf[['gisjoin', 'black_share']],
                                    left_on='GISJOIN', right_on='gisjoin', how='inner')
            cluster_gdf['face_color'] = cluster_gdf['black_share'].apply(lambda x: cmap(norm(x)))
            cluster_gdf.plot(ax=ax, color=cluster_gdf['face_color'].tolist(),
                             edgecolor='grey', linewidth=0.2)

            # buffer=0 outline always shown as a reference
            buf0_tracts = cluster_selections[(cluster_selections['year'] == year) &
                                             (cluster_selections['buffer_size'] == 0)]
            buf0_gdf = gdf.merge(buf0_tracts[['gisjoin']], left_on='GISJOIN', right_on='gisjoin', how='inner')
            gpd.GeoSeries([buf0_gdf.geometry.union_all()], crs=gdf.crs).boundary.plot(
                ax=ax, color='black', linewidth=1.2, zorder=4)

            # medoid star — fixed at buffer=0
            medoid_row = cluster_metrics[(cluster_metrics['year'] == year) &
                                         (cluster_metrics['buffer_size'] == 0)]
            if not medoid_row.empty:
                medoid_gisjoin = medoid_row.iloc[0]['center_gisjoin']
                medoid_geom = gdf.loc[gdf['GISJOIN'] == medoid_gisjoin, 'geometry']
                if not medoid_geom.empty:
                    c = medoid_geom.iloc[0].centroid
                    ax.scatter(c.x, c.y, marker='*', s=60, color='tomato',
                               edgecolor='black', linewidth=0.5, zorder=5)

            if row_i == 0:
                ax.set_title(str(year), fontsize=10)
            if year in year_limits:
                xl, xr, yb, yt = year_limits[year]
                ax.set_xlim(xl, xr)
                ax.set_ylim(yb, yt)
            ax.set_aspect('equal', adjustable='datalim')
            ax.axis('off')

            if col_i == 0:
                ax.text(-0.05, 0.5, f"Buffer {buf}", transform=ax.transAxes,
                        fontsize=9, va='center', ha='right', rotation=90)

    color_scale = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    fig.colorbar(color_scale, ax=axes, label="Black population share", fraction=0.015, pad=0.02)

    fig.subplots_adjust(top=0.95)

    fig.legend(handles=[
        Line2D([0], [0], color='tomato', marker='*', markersize=12, linestyle='None', label='Medoid (buffer = 0)'),
        Line2D([0], [0], color='black', linestyle='-', linewidth=1.2, label='Outline of core cluster (buffer = 0)'),
    ], loc='upper left', bbox_to_anchor=(0.45, 0.985), fontsize=9, frameon=False)

    fig.suptitle(f'{city_name} — {cluster}', fontsize=13, y=0.995)

    figure_path = EXPERIMENT_DIR / "figures" / "choropleths_by_buffers" / f"{city_name}_{cluster}_choropleth_by_buffer.png"
    figure_path.parent.mkdir(exist_ok=True)
    fig.savefig(figure_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved {figure_path}")
