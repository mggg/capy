import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import pandas as pd
import geopandas as gpd
from pathlib import Path


EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
GEO_DIR = EXPERIMENT_DIR.parent.parent / "data" / "processed" / "clipped_geographies"

cmap = plt.cm.viridis

tracts = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_tracts.csv", dtype={'area_code': str, 'gisjoin': str})
metrics = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_metrics.csv", dtype={'area_code': str})

for (area_code, city_name, cluster), tract_selections in tracts.groupby(['area_code', 'city_name', 'cluster'], sort=True):
    print(f"Plotting {city_name}, {cluster}")
    cluster_metrics = metrics[(metrics['area_code'] == area_code) & (metrics['cluster'] == cluster)]
    years = sorted(cluster_metrics['year'].unique())
    all_buffer_sizes = sorted(cluster_metrics['buffer_size'].unique())

    # normalise Moran across all buffers and years for this cluster
    norm = mcolors.Normalize(vmin=cluster_metrics['moran'].min(),
                             vmax=cluster_metrics['moran'].max())

    fig, axes = plt.subplots(1, len(years), figsize=(20, 7))

    for ax, year in zip(axes, years):
        year_metrics = cluster_metrics[cluster_metrics['year'] == year]
        gdf = gpd.read_file(GEO_DIR / str(year) / f'tracts_in_max_city_{area_code}_{year}_march_2020_vintage.gpkg')

        # draw largest buffer first so smaller buffers (higher Moran) end up on top
        for buf in reversed(all_buffer_sizes):
            moran_val = year_metrics[year_metrics['buffer_size'] == buf].iloc[0]['moran']
            buf_tracts = tract_selections[(tract_selections['year'] == year) & (tract_selections['buffer_size'] == buf)]
            buf_gdf = gdf.merge(buf_tracts[['gisjoin']], left_on='GISJOIN', right_on='gisjoin', how='inner')
            if not buf_gdf.empty:
                buf_gdf.plot(ax=ax, color=cmap(norm(moran_val)), edgecolor='grey', linewidth=0.2)

        ax.set_title(str(year), fontsize=11)
        ax.set_aspect('equal')
        ax.axis('off')

    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=axes,
                 label="Moran's I", fraction=0.025, pad=0.02)
    fig.suptitle(f'{city_name} — {cluster}', fontsize=13)
    fig.tight_layout()

    figure_path = EXPERIMENT_DIR / "figures" / "choropleths_by_moran_value" / f"{city_name}_{cluster}_moran_choropleth.png"
    figure_path.parent.mkdir(exist_ok=True)
    fig.savefig(figure_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved {figure_path}")
