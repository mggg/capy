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

norm = mcolors.Normalize(vmin=0, vmax=1)
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

    # layout: 3 rows
    fig = plt.figure(figsize=(20, 15))
    outer_gs = gridspec.GridSpec(3, 1, height_ratios=[3.5, 2.5, 1.5], figure=fig, hspace=0.45)
    top_gs = gridspec.GridSpecFromSubplotSpec(1, len(years), subplot_spec=outer_gs[0], wspace=0.02)
    mid_gs = gridspec.GridSpecFromSubplotSpec(1, len(years), subplot_spec=outer_gs[1], wspace=0.02)
    ax_line = fig.add_subplot(outer_gs[2])

    axes = [fig.add_subplot(top_gs[0, i]) for i in range(len(years))]
    rad_axes = [fig.add_subplot(mid_gs[0, i]) for i in range(len(years))]

    # row 1: choropleth (unchanged)
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

    axes[0].text(2.6, 1.07, "Black population share in the buffered cluster",
                 transform=axes[0].transAxes, ha='center', va='bottom', fontsize=11, clip_on=False)

    color_scale = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    fig.colorbar(color_scale, ax=axes, label="Black population share per tract", fraction=0.025, pad=0.02)

    # row 2: radial panels (true angle from medoid)
    for ax, year in zip(rad_axes, years):
        if year not in radial_by_year:
            ax.axis('off'); continue
        rd = radial_by_year[year]
        panel_radial(ax, rd['coords'], rd['share'], rmax, rd['reach'], title="")

    rad_axes[0].text(2.6, 1.08, "Radial plot, tracts at the true angle from medoid",
                     transform=rad_axes[0].transAxes, ha='center', va='bottom', fontsize=11, clip_on=False)

    # row 3: Moran's I time series, one line per buffer size; we decided to show buffer=3
    # buf_sizes = sorted(cluster_metrics['buffer_size'].unique())
    buf_sizes = [3]
    # buf_colors = [cmap((i + 1) / (len(buf_sizes) + 1)) for i in range(len(buf_sizes))]
    buf_colors = ["#073874"]
    for buf, color in zip(buf_sizes, buf_colors):
        sub = cluster_metrics[cluster_metrics['buffer_size'] == buf].sort_values('year')
        ax_line.plot(sub['year'], sub['moran'], color=color,
                     marker='o', markersize=4, linewidth=1.2) #, label=f"Moran's I, buffer size: {buf}")
        # ax_line.plot(sub['year'], sub['half_edge'], color='tomato', marker='o', markersize=4, linewidth=1.2, label=f"Half Edge, buffer size: {buf}")

    ax_line2 = ax_line.twinx()
    ax_line2.plot(sub['year'], sub['half_edge'], color='tomato',
                marker='o', markersize=4, linewidth=1.2,)# label=f"Half Edge, buffer size: {buf}")
    ax_line2.set_ylabel("Half Edge", fontsize=9, color = 'tomato')

    # ax_line.set_xlabel("Year", fontsize=9)
    ax_line.set_ylabel("Moran's I", fontsize=9, color="#073874")
    ax_line.set_title(f"Moran's I and Capy", fontsize=11, loc='center', pad = 10)

    ax_line.tick_params(axis='y', colors='#094996', size=2)
    ax_line2.tick_params(axis='y', colors='tomato', size=2)
    # h1, l1 = ax_line.get_legend_handles_labels()
    # h2, l2 = ax_line2.get_legend_handles_labels()
    # ax_line.legend(h1 + h2, l1 + l2, fontsize=7, frameon=False)

    ax_line.set_xticks(years)
    ax_line.set_xticklabels([str(y) for y in years], fontsize=8)
    # ax_line.legend(fontsize=7, ncol=min(len(buf_sizes), 6), loc='best', frameon=False)

    ax_line2.spines[['top', 'bottom', 'left', 'right']].set_edgecolor('#cccccc')

    fig.legend(handles=[Line2D([0], [0], color='tomato', marker='*', markersize=12,
               linestyle='None', label="Cluster medoid tract"),
               Line2D([0], [0], color='black', markersize=12, linestyle='-',
               label='Outline of the original cluster')],
    loc='upper left', bbox_to_anchor=(0.37, 0.95), fontsize=9, frameon=False, ncol=2)

    fig.suptitle(f'{city_name}, {cluster}', fontsize=14)
    fig.text(0.5, 0.962,
             f"Buffer size {DISPLAY_BUFFER} shown. Cluster boundary defined by edge-distance in the 2020 dual graph, back-projected geometrically to each decade.",
             ha='center', va='top', fontsize=8, color="#474747")

    figure_path = (EXPERIMENT_DIR / "figures" / "metrics_heatmap_by_buffers"
                   / f"{city_name}_{cluster}_choropleth_radial_morans.png")
    figure_path.parent.mkdir(exist_ok=True)
    fig.savefig(figure_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved {figure_path}")
