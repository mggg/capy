import sys
from pathlib import Path
import json
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
import pandas as pd
import geopandas as gpd
import networkx as nx

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXPERIMENT_DIR))

from utils.viz_helpers import bfs, bearings, radial_coords, panel_radial

GEO_DIR = EXPERIMENT_DIR.parent.parent / "data" / "processed" / "clipped_geographies"
GRAPHS_DIR = EXPERIMENT_DIR.parent.parent / "data" / "processed" / "dual_graphs"

cmap = plt.cm.Blues

DISPLAY_BUFFER = 2

tracts = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_tracts.csv",
                     dtype={'area_code': str, 'gisjoin': str})
tracts['black_share'] = (tracts['black_population']
                         / (tracts['black_population'] + tracts['white_population']))

metrics = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_metrics.csv",
                      dtype={'area_code': str, 'center_gisjoin': str})


def load_graph(area_code, year):
    path = GRAPHS_DIR / str(year) / f"tracts_in_max_city_{area_code}_{year}_march_2020_vintage_orig.json"
    raw  = json.loads(path.read_text())
    G = nx.Graph()
    for attrs in raw["nodes"]:
        attrs = dict(attrs)
        G.add_node(attrs.pop("id"), **attrs)
    order = [n["id"] for n in raw["nodes"]]
    for node, neighbours in zip(order, raw["adjacency"]):
        for edge in neighbours:
            G.add_edge(node, edge["id"])
    return G


def get_radial_data(area_code, year, year_tracts_df, medoid_gisjoin):
    """Load graph, run BFS from medoid, return radial coords + black_share keyed by node_id."""
    try:
        G = load_graph(area_code, year)
    except FileNotFoundError:
        return None
    gisjoin_to_node = {G.nodes[n]["GISJOIN"]: n for n in G}
    root = gisjoin_to_node.get(medoid_gisjoin)
    if root is None:
        return None
    d = bfs(G, root)
    rows = [(gisjoin_to_node[gj], share)
            for gj, share in zip(year_tracts_df["gisjoin"], year_tracts_df["black_share"])
            if gj in gisjoin_to_node and gisjoin_to_node[gj] in d]
    if not rows:
        return None
    nodes = [n for n, _ in rows]
    share_by_node = {n: s for n, s in rows}
    theta = bearings(G, root, nodes)
    coords = radial_coords(d, theta, nodes)
    reach = max(d[n] for n in nodes)
    return {"coords": coords, "share": share_by_node, "reach": reach}


for (area_code, city_name, cluster), tract_selections in tracts.groupby(['area_code', 'city_name', 'cluster'], sort=True):
    print(f"Plotting {city_name}, {cluster}")
    tracts_buf3 = tract_selections[tract_selections['buffer_size'] == DISPLAY_BUFFER]
    cluster_metrics = metrics[(metrics['area_code'] == area_code) & (metrics['cluster'] == cluster)]
    years = sorted(cluster_metrics['year'].unique())

    # pre-pass: compute radial data for all years so rmax can be shared across panels
    radial_by_year = {}
    for year in years:
        year_tracts = tracts_buf3[tracts_buf3['year'] == year]
        med_row = cluster_metrics[(cluster_metrics['year'] == year)
                                & (cluster_metrics['buffer_size'] == 0)]
        if med_row.empty or year_tracts.empty:
            continue
        rd = get_radial_data(area_code, year, year_tracts, med_row.iloc[0]['center_gisjoin'])
        if rd is not None:
            radial_by_year[year] = rd

    rmax = max(rd['reach'] for rd in radial_by_year.values()) if radial_by_year else 1

    # TwoSlopeNorm centered at the per-cluster median: half the colormap covers
    # 0→median, half covers median→1, so both the buffer tracts and the core
    # tracts get equal color resolution regardless of how skewed the distribution is
    _shares = tracts_buf3['black_share'].dropna()
    norm = mcolors.TwoSlopeNorm(#vcenter=_shares.median(),
                                 vmin=0, vmax=0.8)

    figure_dir = EXPERIMENT_DIR / "figures" / "metrics_panels_by_buffers"
    figure_dir.mkdir(parents=True, exist_ok=True)

    fig_width = 4 * len(years)  # shared width across all three figures

    # --- figure 1: choropleth ---
    fig_choro, axes = plt.subplots(1, len(years), figsize=(fig_width, 4.5))
    if len(years) == 1:
        axes = [axes]

    for ax, year in zip(axes, years):
        year_selections = tracts_buf3[tracts_buf3['year'] == year]
        med_row = cluster_metrics[(cluster_metrics['year'] == year)
                                & (cluster_metrics['buffer_size'] == 0)]
        if med_row.empty:
            ax.axis('off'); continue
        medoid_gisjoin = med_row.iloc[0]['center_gisjoin']

        geo_path = GEO_DIR / str(year) / f'tracts_in_max_city_{area_code}_{year}_march_2020_vintage.gpkg'
        gdf = gpd.read_file(geo_path)
        cluster_gdf = gdf.merge(year_selections[['gisjoin', 'black_share']],
                                left_on='GISJOIN', right_on='gisjoin', how='inner')
        cluster_gdf['choropleth_color'] = cluster_gdf['black_share'].apply(lambda x: cmap(norm(x)))
        cluster_gdf.plot(ax=ax, color=cluster_gdf['choropleth_color'].tolist(),
                         edgecolor='grey', linewidth=0.2)

        buf0_tracts = tract_selections[(tract_selections['year'] == year)
                                       & (tract_selections['buffer_size'] == 0)]
        buf0_gdf = gdf.merge(buf0_tracts[['gisjoin']], left_on='GISJOIN', right_on='gisjoin', how='inner')
        gpd.GeoSeries([buf0_gdf.geometry.union_all()], crs=gdf.crs).boundary.plot(
            ax=ax, color='black', linewidth=1.5, zorder=4)

        medoid_geom = gdf.loc[gdf['GISJOIN'] == medoid_gisjoin, 'geometry']
        if not medoid_geom.empty:
            c = medoid_geom.iloc[0].centroid
            ax.scatter(c.x, c.y, marker='*', s=50, color='tomato',
                       edgecolor='black', linewidth=0.5, zorder=5)

        ax.set_title(str(year), fontsize=9)
        ax.set_aspect('equal')
        ax.axis('off')

    color_scale = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cbar = fig_choro.colorbar(color_scale, ax=axes, label="Black population share per tract", fraction=0.025, pad=0.02)

    # mark the median on the colorbar — with TwoSlopeNorm the median (vcenter)
    # always sits at the visual center (y=0.5 in axes coordinates)
    median_val = _shares.median()
    ticks = sorted({round(t, 2) for t in cbar.get_ticks()} | {round(median_val, 2)})
    ticks = [t for t in ticks if 0.0 <= t <= 1.0]
    cbar.set_ticks(ticks)
    cbar.set_ticklabels([
        f'{t:.2f} (median)' if abs(t - median_val) < 0.005 else f'{t:.2f}'
        for t in ticks
    ])
    cbar.ax.tick_params(labelsize=7)
    cbar.ax.plot([0, 1], [0.5, 0.5], color='#444444', linewidth=1.0, linestyle='--',
                 transform=cbar.ax.transAxes, clip_on=False)
    fig_choro.legend(handles=[Line2D([0], [0], color='tomato', marker='*', markersize=12,
               linestyle='None', label="Cluster medoid tract"),
               Line2D([0], [0], color='black', markersize=12, linestyle='-',
               label='Outline of the original cluster')],
    loc='lower center', bbox_to_anchor=(0.5, -0.06), fontsize=9, frameon=False, ncol=2)
    # fig_choro.suptitle(f'{city_name}, {cluster}', fontsize=14)

    choro_path = figure_dir / f"{city_name}_{cluster}_choropleth.png"
    fig_choro.savefig(choro_path, dpi=200, bbox_inches='tight')
    plt.close(fig_choro)
    print(f"Saved {choro_path}")

    # --- figure 2: radial ---
    fig_radial, rad_axes = plt.subplots(1, len(years), figsize=(fig_width, 4.5))
    if len(years) == 1:
        rad_axes = [rad_axes]

    for ax, year in zip(rad_axes, years):
        if year not in radial_by_year:
            ax.axis('off'); continue
        rd = radial_by_year[year]
        panel_radial(ax, rd['coords'], rd['share'], rmax, rd['reach'], title=str(year))

    # fig_radial.suptitle(f'{city_name}, {cluster}', fontsize=14)

    radial_path = figure_dir / f"{city_name}_{cluster}_radial.png"
    fig_radial.savefig(radial_path, dpi=200, bbox_inches='tight')
    plt.close(fig_radial)
    print(f"Saved {radial_path}")

    # --- figure 3: line plot ---
    fig_line, ax_line = plt.subplots(figsize=(fig_width, 3))

    # buf_sizes = sorted(cluster_metrics['buffer_size'].unique())
    buf_sizes = [3]
    # buf_colors = [cmap((i + 1) / (len(buf_sizes) + 1)) for i in range(len(buf_sizes))]
    buf_colors = ["#073874"]
    for buf, color in zip(buf_sizes, buf_colors):
        sub = cluster_metrics[cluster_metrics['buffer_size'] == buf].sort_values('year')
        ax_line.plot(sub['year'], sub['moran'], color=color,
                     marker='o', markersize=4, linewidth=2) #, label=f"Moran's I, buffer size: {buf}")
        # ax_line.plot(sub['year'], sub['half_edge'], color='tomato', marker='o', markersize=4, linewidth=1.2, label=f"Half Edge, buffer size: {buf}")

    ax_line2 = ax_line.twinx()
    ax_line2.plot(sub['year'], sub['half_edge'], color='tomato',
                marker='o', markersize=4, linewidth=2, alpha = 0.8)# label=f"Half Edge, buffer size: {buf}")
    ax_line2.set_ylabel("Capy", fontsize=9, color='tomato', labelpad=-15)

    # ax_line.set_xlabel("Year", fontsize=9)
    ax_line.set_ylabel("Moran's I", fontsize=9, color="#073874", labelpad=-15)
    # ax_line.set_title(f"Moran's I and Capy", fontsize=11, loc='center', pad=10)

    ax_line.set_yticks([sub['moran'].min(), sub['moran'].max()],
                       labels=[f"{sub['moran'].min():.2f}", f"{sub['moran'].max():.2f}"])
    ax_line2.set_yticks([sub['half_edge'].min(), sub['half_edge'].max()],
                        labels=[f"{sub['half_edge'].min():.2f}", f"{sub['half_edge'].max():.2f}"])
    ax_line.tick_params(axis='y', colors='#094996', size=2)
    ax_line2.tick_params(axis='y', colors='tomato', size=2)
    # h1, l1 = ax_line.get_legend_handles_labels()
    # h2, l2 = ax_line2.get_legend_handles_labels()
    # ax_line.legend(h1 + h2, l1 + l2, fontsize=7, frameon=False)

    ax_line.set_xticks(years)
    ax_line.set_xticklabels([str(y) for y in years], fontsize=8)
    # ax_line.legend(fontsize=7, ncol=min(len(buf_sizes), 6), loc='best', frameon=False)

    ax_line2.spines[['top', 'bottom', 'left', 'right']].set_edgecolor('#cccccc')
    # fig_line.suptitle(f'{city_name}, {cluster}', fontsize=14)

    lines_path = figure_dir / f"{city_name}_{cluster}_lines.png"
    fig_line.savefig(lines_path, dpi=200, bbox_inches='tight')
    plt.close(fig_line)
    print(f"Saved {lines_path}")
