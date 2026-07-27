import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
GEO_DIR = EXPERIMENT_DIR.parent.parent / "data" / "processed" / "clipped_geographies"

CBSA_selections = pd.read_csv(
    EXPERIMENT_DIR / "data" / "manual_cluster_tracts.csv",
    dtype={'cbsa': str, 'gisjoin': str})
CBSA_metrics = pd.read_csv(
    EXPERIMENT_DIR / "data" / "cluster_metrics.csv",
    dtype={'cbsa': str, 'center_gisjoin': str})
CBSA_selections = CBSA_selections[CBSA_selections['cbsa'] == '16980']
CBSA_metrics = CBSA_metrics[CBSA_metrics['cbsa'] == '16980']
years = sorted(CBSA_metrics['year'].unique())
# colors = {'hyde_park': "#b82ca5", 'austin': "#d69169"}

# max_black_count = CBSA_selections["black_population"].max()
# norm = mcolors.Normalize(vmin=0, vmax=max_black_count)
norm = mcolors.Normalize(vmin=0, vmax=1)
cmap = plt.cm.Blues

fig, axes = plt.subplots(1, len(years), figsize=(20, 7))

for ax, year in zip(axes, years):
    geo_path = GEO_DIR / str(year) / f'tracts_in_cbsa_16980_{year}_march_2020_vintage.gpkg'
    gdf = gpd.read_file(geo_path)

    year_selections = CBSA_selections[CBSA_selections['year'] == year]

    cluster_gdf = gdf.merge(
        year_selections[['gisjoin', 'cluster', 'black_population', 'black_share']],
        left_on='GISJOIN', right_on='gisjoin', how='inner')
    # cluster_gdf['face_color'] = cluster_gdf['black_population'].apply(
    #     lambda x: cmap(norm(x)))
    cluster_gdf['face_color'] = cluster_gdf['black_share'].apply(
        lambda x: cmap(norm(x)))
    cluster_gdf.plot(ax=ax, color=cluster_gdf['face_color'].tolist(),
                     edgecolor='grey', linewidth=0.2)

    # Medoid star and annotation
    for _, row in CBSA_metrics[CBSA_metrics['year'] == year].iterrows():
        cluster = row['cluster']
        medoid_gisjoin = row['center_gisjoin']

        medoid_geom = gdf.loc[gdf['GISJOIN'] == medoid_gisjoin, 'geometry']
        if medoid_geom.empty:
            continue
        centroid = medoid_geom.iloc[0].centroid
        ax.scatter(centroid.x, centroid.y, marker='*', s=50,
                #    color=colors.get(cluster, 'red'),
                color = "tomato",
                   edgecolor='black', linewidth=0.5, zorder=5)

        medoid_data = year_selections[
            (year_selections['cluster'] == cluster) &
            (year_selections['gisjoin'] == medoid_gisjoin)]
        if medoid_data.empty:
            continue
        bp = medoid_data['black_population'].iloc[0]
        bs = medoid_data['black_share'].iloc[0]
        # if cluster == 'hyde_park':
        ax.annotate(
            f"Medoid's Black population: {bp} ({bs:.1%})",
            xy=(1, 0), xycoords='axes fraction',
            ha='right', va='top', fontsize=10, color='black')
        # else:
        #     ax.annotate(
        #         f"\n\n{cluster}: {bp} ({bs:.1%})",
        #         xy=(1, 0), xycoords='axes fraction',
        #         ha='right', va='top', fontsize=10, color='black')

    ax.set_title(str(year))
    ax.set_aspect('equal')
    ax.axis('off')

legend_items = [
    Line2D([0], [0], color='black', marker='*', markersize=13,
           linestyle='None', label='Selected medoid')]
fig.legend(handles=legend_items, loc='lower center', ncol=3)
fig.suptitle('Chicago South Side cluster and Black-population-weighted medoids')
fig.tight_layout(rect=(0, 0.08, 1, 0.94))

color_scale = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
fig.colorbar(color_scale, ax=axes, label="Black population share",
             fraction=0.025, pad=0.02)

figure_path = EXPERIMENT_DIR / "figures" / "chicago_cluster_choropleth_all_years.png"
figure_path.parent.mkdir(exist_ok=True)
fig.savefig(figure_path, dpi=200, bbox_inches='tight')
plt.show()
