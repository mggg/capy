import argparse
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

parser = argparse.ArgumentParser()
parser.add_argument("--cluster_title", default="South Side",
                    help="Cluster title, e.g. 'South Side' or 'Philadelphia, Germantown'")
args = parser.parse_args()
CLUSTER_TITLE = args.cluster_title

# Build a lookup that accepts both plain titles ("Germantown") and
# city-prefixed titles ("Philadelphia, Germantown") as used in cluster_changes.csv
_CBSA_CITY = {"16980": "Chicago", "37980": "Philadelphia"}
_all = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_tracts.csv",
                   dtype={'cbsa': str, 'gisjoin': str})
_title_map = {}
for _, r in _all[["cbsa", "cluster", "cluster_title"]].drop_duplicates().iterrows():
    _title_map[r["cluster_title"]] = (r["cbsa"], r["cluster"])
    city = _CBSA_CITY.get(r["cbsa"], "")
    if city:
        _title_map[f"{city}, {r['cluster_title']}"] = (r["cbsa"], r["cluster"])

if CLUSTER_TITLE not in _title_map:
    raise ValueError(
        f"Unknown --cluster_title {CLUSTER_TITLE!r}. "
        f"Available: {sorted(_title_map)}")
CBSA, CLUSTER = _title_map[CLUSTER_TITLE]

CBSA_selections = _all[(_all['cbsa'] == CBSA) & (_all['cluster'] == CLUSTER)]
CBSA_metrics = pd.read_csv(EXPERIMENT_DIR / "data" / "cluster_metrics.csv",
    dtype={'cbsa': str, 'center_gisjoin': str})
CBSA_metrics = CBSA_metrics[(CBSA_metrics['cbsa'] == CBSA) & (CBSA_metrics['cluster'] == CLUSTER)]
years = sorted(CBSA_metrics['year'].unique())

max_black_count = CBSA_selections["black_population"].max()
max_log_black = np.log1p(max_black_count)
# norm = mcolors.Normalize(vmin=0, vmax=max_black_count)  # by count
# norm = mcolors.Normalize(vmin=0, vmax=1)  # by share
norm = mcolors.Normalize(vmin=0, vmax=max_log_black)  # by log count
cmap = plt.cm.Blues

gdfs = {
    year: gpd.read_file(
        GEO_DIR / str(year) / f'tracts_in_cbsa_{CBSA}_{year}_march_2020_vintage.gpkg')
    for year in years}

# Compute a fixed bounding box across all years so the map doesn't shift between frames
all_cluster_gdfs = [
    gdfs[year].merge(
        CBSA_selections[CBSA_selections['year'] == year][['gisjoin']],
        left_on='GISJOIN', right_on='gisjoin', how='inner')
    for year in years]
combined = gpd.GeoDataFrame(pd.concat(all_cluster_gdfs, ignore_index=True))
minx, miny, maxx, maxy = combined.total_bounds
pad_x = (maxx - minx) * 0.03
pad_y = (maxy - miny) * 0.03
fixed_xlim = (minx - pad_x, maxx + pad_x)
fixed_ylim = (miny - pad_y, maxy + pad_y)

all_mass = {
    int(row['year']): int(row['area_black_population'])
    for _, row in CBSA_metrics.iterrows()}
all_spread = {
    int(row['year']): float(row['spread'])
    for _, row in CBSA_metrics.iterrows()}
mass_max = max(all_mass.values())
spread_min = min(all_spread.values()) * 0.95
spread_max = max(all_spread.values()) * 1.05

frames = []
for year in years:
    fig, (ax_map, ax_line) = plt.subplots(
        2, 1, figsize=(8, 9), layout='constrained',
        gridspec_kw={'height_ratios': [5, 1], 'hspace': 0.15})

    gdf = gdfs[year]
    year_selections = CBSA_selections[CBSA_selections['year'] == year]

    cluster_gdf = gdf.merge(
        year_selections[['gisjoin', 'cluster', 'black_population', 'black_share']],
        left_on='GISJOIN', right_on='gisjoin', how='inner')
    # cluster_gdf['face_color'] = cluster_gdf['black_population'].apply(
    #     lambda x: cmap(norm(x)))  # by count
    # cluster_gdf['face_color'] = cluster_gdf['black_share'].apply(
    #     lambda x: cmap(norm(x)))  # by share
    cluster_gdf['face_color'] = cluster_gdf['black_population'].apply(
        lambda x: cmap(norm(np.log1p(x))))  # by log count
    cluster_gdf.plot(ax=ax_map, color=cluster_gdf['face_color'].tolist(),
                     edgecolor='grey', linewidth=0.2)

    for _, row in CBSA_metrics[CBSA_metrics['year'] == year].iterrows():
        cluster = row['cluster']
        medoid_gisjoin = row['center_gisjoin']

        medoid_geom = gdf.loc[gdf['GISJOIN'] == medoid_gisjoin, 'geometry']
        if medoid_geom.empty:
            continue
        centroid = medoid_geom.iloc[0].centroid
        ax_map.scatter(centroid.x, centroid.y, marker='*', s=50,
                       color='tomato', edgecolor='black', linewidth=0.5, zorder=5)

        medoid_data = year_selections[
            (year_selections['cluster'] == cluster) &
            (year_selections['gisjoin'] == medoid_gisjoin)]
        if medoid_data.empty:
            continue
        bp = medoid_data['black_population'].iloc[0]
        bs = medoid_data['black_share'].iloc[0]
        # ax_map.annotate(
        #     f"Medoid's Black population: {bp} ({bs:.1%})",
        #     xy=(1, 0), xycoords='axes fraction',
        #     ha='right', va='top', fontsize=10, color='black')

    ax_map.set_xlim(fixed_xlim)
    ax_map.set_ylim(fixed_ylim)
    ax_map.set_title(str(year), fontsize=14)
    ax_map.set_aspect('equal')
    ax_map.axis('off')

    # Cumulative mass + spread line plot
    years_so_far = [y for y in years if y <= year]
    mass_so_far = [all_mass[y] for y in years_so_far]
    spread_so_far = [all_spread[y] for y in years_so_far]

    ax_line.plot(years_so_far, mass_so_far, color='steelblue', linewidth=1.5,
                 marker='o', markersize=4, zorder=2)
    ax_line.scatter([year], [all_mass[year]], color='tomato', s=50, zorder=3)
    ax_line.set_xlim(years[0] - 3, years[-1] + 3)
    ax_line.set_ylim(0, mass_max * 1.15)
    ax_line.set_xticks(years)
    ax_line.set_ylabel('Mass\n(Black pop.)', fontsize=8, color='steelblue')
    ax_line.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, _: f'{x/1e3:.0f}k'))
    ax_line.tick_params(labelsize=8, axis='y', labelcolor='steelblue')
    ax_line.tick_params(labelsize=8, axis='x')
    for spine in ['top']:
        ax_line.spines[spine].set_visible(False)
    ax_line.spines['left'].set_color('steelblue')

    ax_spread = ax_line.twinx()
    ax_spread.plot(years_so_far, spread_so_far, color='darkorange', linewidth=1.5,
                   marker='o', markersize=4, zorder=2)#, linestyle='--')
    ax_spread.scatter([year], [all_spread[year]], color='tomato', s=50, zorder=3)
    ax_spread.set_ylim(spread_min, spread_max)
    ax_spread.set_ylabel('Spread', fontsize=8, color='darkorange')
    ax_spread.tick_params(labelsize=8, axis='y', labelcolor='darkorange')
    ax_spread.spines['top'].set_visible(False)
    ax_spread.spines['right'].set_color('darkorange')

    legend_items = [
        Line2D([0], [0], color='tomato', marker='*', markersize=13,
               linestyle='None', label='Selected medoid')]
    fig.legend(handles=legend_items, loc='upper left', bbox_to_anchor=(0.05, 0.89), fontsize=9, frameon=False)
    fig.suptitle(f'CBSA {CBSA} — {CLUSTER_TITLE}')

    color_scale = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    fig.colorbar(color_scale, ax=ax_map, label="Log(Black population + 1)",
                 fraction=0.025, pad=0.02)


    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    frames.append(Image.open(buf).copy())
    buf.close()
    plt.close(fig)

figure_title = CLUSTER_TITLE.replace(' ', '_').replace(',', '').lower()
gif_path = EXPERIMENT_DIR / "figures" / f"{figure_title}_choropleth_decades.gif"
gif_path.parent.mkdir(exist_ok=True)
frames[0].save(
    gif_path,
    save_all=True,
    append_images=frames[1:],
    loop=0,
    duration=1500)
print(f"Saved to {gif_path}")
