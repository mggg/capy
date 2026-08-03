import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
import pandas as pd
import geopandas as gpd
from pathlib import Path

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
GEO_DIR = EXPERIMENT_DIR.parent.parent / "data" / "processed" / "clipped_geographies"

norm = mcolors.Normalize(vmin=0, vmax=1)
cmap = plt.cm.Blues

all_selections = pd.read_csv(
    EXPERIMENT_DIR / "data" / "auto_cluster_tracts.csv",
    dtype={'area_code': str, 'gisjoin': str})
all_metrics = pd.read_csv(
    EXPERIMENT_DIR / "data" / "cluster_metrics.csv",
    dtype={'area_code': str, 'center_gisjoin': str})

for (area_code, cluster), cluster_selections in all_selections.groupby(['area_code', 'cluster'], sort=True):
    cluster_metrics = all_metrics[
        (all_metrics['area_code'] == area_code) & (all_metrics['cluster'] == cluster)]
    years = sorted(cluster_metrics['year'].unique())

    fig, axes = plt.subplots(1, len(years), figsize=(20, 7))

    for ax, year in zip(axes, years):
        geo_path = GEO_DIR / str(year) / f'tracts_in_max_city_{area_code}_{year}_march_2020_vintage.gpkg'
        gdf = gpd.read_file(geo_path)

        year_selections = cluster_selections[cluster_selections['year'] == year]

        cluster_gdf = gdf.merge(
            year_selections[['gisjoin', 'cluster', 'black_population', 'black_share']],
            left_on='GISJOIN', right_on='gisjoin', how='inner')
        cluster_gdf['face_color'] = cluster_gdf['black_share'].apply(lambda x: cmap(norm(x)))
        cluster_gdf.plot(ax=ax, color=cluster_gdf['face_color'].tolist(),
                         edgecolor='grey', linewidth=0.2)

        gpd.GeoSeries([cluster_gdf.geometry.unary_union], crs=cluster_gdf.crs).boundary.plot(
            ax=ax, color='black', linewidth=1.5, zorder=4)

        for _, row in cluster_metrics[cluster_metrics['year'] == year].iterrows():
            medoid_gisjoin = row['center_gisjoin']
            medoid_geom = gdf.loc[gdf['GISJOIN'] == medoid_gisjoin, 'geometry']
            if medoid_geom.empty:
                continue
            centroid = medoid_geom.iloc[0].centroid
            ax.scatter(centroid.x, centroid.y, marker='*', s=50,
                       color='tomato', edgecolor='black', linewidth=0.5, zorder=5)

        ax.set_title(str(year))
        ax.set_aspect('equal')
        ax.axis('off')

    fig.legend(
        handles=[Line2D([0], [0], color='black', marker='*', markersize=13,
                        linestyle='None', label='Selected medoid')],
        loc='lower center', ncol=3)

    cluster_title = (cluster_selections["cluster_title"].iloc[0]
                     if "cluster_title" in cluster_selections.columns
                     else cluster)
    fig.suptitle(f'{area_code} — {cluster_title} and Black-population-weighted medoids')
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))

    color_scale = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    fig.colorbar(color_scale, ax=axes, label="Black population share",
                 fraction=0.025, pad=0.02)

    figure_title = cluster_title.replace(' ', '_').replace(',', '').lower()
    figure_path = EXPERIMENT_DIR / "figures" / f"{figure_title}_choropleth_all_years.png"
    figure_path.parent.mkdir(exist_ok=True)
    fig.savefig(figure_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved {figure_path}")
