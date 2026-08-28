import io
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
import geopandas as gpd
from pathlib import Path
from PIL import Image

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
GEO_DIR = EXPERIMENT_DIR.parent.parent / "data" / "processed" / "clipped_geographies"

all_selections = pd.read_csv(
    EXPERIMENT_DIR / "data" / "auto_cluster_tracts.csv",
    dtype={'area_code': str, 'gisjoin': str})
all_metrics = pd.read_csv(
    EXPERIMENT_DIR / "data" / "cluster_metrics.csv",
    dtype={'area_code': str, 'center_gisjoin': str})

for (area_code, cluster), cluster_selections in all_selections.groupby(['area_code', 'cluster'], sort=True):
    cluster = cluster_selections["cluster"].iloc[0]
    cluster_metrics = all_metrics[
        (all_metrics['area_code'] == area_code) & (all_metrics['cluster'] == cluster)]
    years = sorted(cluster_metrics['year'].unique())

    max_black_count = cluster_selections["black_population"].max()
    max_log_black = np.log1p(max_black_count)
    norm = mcolors.Normalize(vmin=0, vmax=max_log_black)
    cmap = plt.cm.Blues

    gdfs = {
        year: gpd.read_file(
            GEO_DIR / str(year) / f'tracts_in_max_city_{area_code}_{year}_march_2020_vintage.gpkg')
        for year in years}

    all_cluster_gdfs = [
        gdfs[year].merge(
            cluster_selections[cluster_selections['year'] == year][['gisjoin']],
            left_on='GISJOIN', right_on='gisjoin', how='inner')
        for year in years]
    combined = gpd.GeoDataFrame(pd.concat(all_cluster_gdfs, ignore_index=True))
    minx, miny, maxx, maxy = combined.total_bounds
    pad_x = (maxx - minx) * 0.03
    pad_y = (maxy - miny) * 0.03
    fixed_xlim = (minx - pad_x, maxx + pad_x)
    fixed_ylim = (miny - pad_y, maxy + pad_y)

    all_mass = {int(row['year']): int(row['area_black_population']) for _, row in cluster_metrics.iterrows()}
    all_spread = {int(row['year']): float(row['spread']) for _, row in cluster_metrics.iterrows()}
    mass_max = max(all_mass.values())
    spread_min = min(all_spread.values()) * 0.95
    spread_max = max(all_spread.values()) * 1.05

    frames = []
    for year in years:
        fig, (ax_map, ax_line) = plt.subplots(
            2, 1, figsize=(8, 9), layout='constrained',
            gridspec_kw={'height_ratios': [5, 1], 'hspace': 0.15})

        gdf = gdfs[year]
        year_selections = cluster_selections[cluster_selections['year'] == year]

        cluster_gdf = gdf.merge(
            year_selections[['gisjoin', 'cluster', 'black_population', 'black_share']],
            left_on='GISJOIN', right_on='gisjoin', how='inner')
        cluster_gdf['face_color'] = cluster_gdf['black_population'].apply(
            lambda x: cmap(norm(np.log1p(x))))
        cluster_gdf.plot(ax=ax_map, color=cluster_gdf['face_color'].tolist(),
                         edgecolor='grey', linewidth=0.2)

        for _, row in cluster_metrics[cluster_metrics['year'] == year].iterrows():
            medoid_gisjoin = row['center_gisjoin']
            medoid_geom = gdf.loc[gdf['GISJOIN'] == medoid_gisjoin, 'geometry']
            if medoid_geom.empty:
                continue
            centroid = medoid_geom.iloc[0].centroid
            ax_map.scatter(centroid.x, centroid.y, marker='*', s=50,
                           color='tomato', edgecolor='black', linewidth=0.5, zorder=5)

        ax_map.set_xlim(fixed_xlim)
        ax_map.set_ylim(fixed_ylim)
        ax_map.set_title(str(year), fontsize=14)
        ax_map.set_aspect('equal')
        ax_map.axis('off')

        years_so_far = [y for y in years if y <= year]
        ax_line.plot(years_so_far, [all_mass[y] for y in years_so_far],
                     color='steelblue', linewidth=1.5, marker='o', markersize=4, zorder=2)
        ax_line.scatter([year], [all_mass[year]], color='tomato', s=50, zorder=3)
        ax_line.set_xlim(years[0] - 3, years[-1] + 3)
        ax_line.set_ylim(0, mass_max * 1.15)
        ax_line.set_xticks(years)
        ax_line.set_ylabel('Mass\n(Black pop.)', fontsize=8, color='steelblue')
        ax_line.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x/1e3:.0f}k'))
        ax_line.tick_params(labelsize=8, axis='y', labelcolor='steelblue')
        ax_line.tick_params(labelsize=8, axis='x')
        ax_line.spines['top'].set_visible(False)
        ax_line.spines['left'].set_color('steelblue')

        ax_spread = ax_line.twinx()
        ax_spread.plot(years_so_far, [all_spread[y] for y in years_so_far],
                       color='darkorange', linewidth=1.5, marker='o', markersize=4, zorder=2)
        ax_spread.scatter([year], [all_spread[year]], color='tomato', s=50, zorder=3)
        ax_spread.set_ylim(spread_min, spread_max)
        ax_spread.set_ylabel('Spread', fontsize=8, color='darkorange')
        ax_spread.tick_params(labelsize=8, axis='y', labelcolor='darkorange')
        ax_spread.spines['top'].set_visible(False)
        ax_spread.spines['right'].set_color('darkorange')

        fig.legend(
            handles=[Line2D([0], [0], color='tomato', marker='*', markersize=13,
                            linestyle='None', label='Selected medoid')],
            loc='upper left', bbox_to_anchor=(0.05, 0.89), fontsize=9, frameon=False)
        fig.suptitle(f'{area_code} — {cluster}')

        color_scale = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        fig.colorbar(color_scale, ax=ax_map, label="Log(Black population + 1)",
                     fraction=0.025, pad=0.02)

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        frames.append(Image.open(buf).copy())
        buf.close()
        plt.close(fig)

    figure_title = cluster.replace(' ', '_').replace(',', '').lower()
    gif_path = EXPERIMENT_DIR / "figures" / f"{figure_title}_choropleth_decades.gif"
    gif_path.parent.mkdir(exist_ok=True)
    frames[0].save(gif_path, save_all=True, append_images=frames[1:], loop=0, duration=1500)
    print(f"Saved to {gif_path}")
