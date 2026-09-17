import sys
from pathlib import Path
import json
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.gridspec as gridspec
import matplotlib.patheffects as pe
from matplotlib.lines import Line2D
from shapely.geometry import Polygon, MultiPolygon
import pandas as pd
import geopandas as gpd
import networkx as nx

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(EXPERIMENT_DIR.parent))

from visualization_settings import BLUE, RADIAL_BASELINE, TANGERINE, bfs, bearings, radial_coords, panel_radial, CMAP_BLACK_SHARE

GEO_DIR = ROOT / "data" / "shared" / "processed" / "clipped_geographies"
GRAPHS_DIR = ROOT / "data" / "shared" / "processed" / "dual_graphs"

cmap = CMAP_BLACK_SHARE

DISPLAY_BUFFER = 2

tracts = pd.read_csv(ROOT / "data" / "experiment_specific" / "observed_diffusion_data" / "auto_cluster_tracts.csv",
                     dtype={'area_code': str, 'gisjoin': str})
tracts['black_share'] = (tracts['black_population']
                         / (tracts['black_population'] + tracts['white_population']))

metrics = pd.read_csv(ROOT / "data" / "experiment_specific" / "observed_diffusion_data" / "auto_cluster_metrics.csv",
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
    medoid = gisjoin_to_node.get(medoid_gisjoin)
    if medoid is None:
        return None
    d = bfs(G, medoid)
    rows = [(gisjoin_to_node[gj], share)
            for gj, share in zip(year_tracts_df["gisjoin"], year_tracts_df["black_share"])
            if gj in gisjoin_to_node and gisjoin_to_node[gj] in d]
    if not rows:
        return None
    nodes = [n for n, _ in rows]
    share_by_node = {n: s for n, s in rows}
    theta = bearings(G, medoid, nodes)
    coords = radial_coords(d, theta, nodes)
    reach = max(d[n] for n in nodes)
    return {"coords": coords, "share": share_by_node, "reach": reach}


figure_dir = ROOT / "figures" / "observed_diffusion" / "metrics_panels_by_buffers"
figure_dir.mkdir(parents=True, exist_ok=True)

norm = mcolors.Normalize(vmin=0.3, vmax=1)

_legend_handles = [
    Line2D([0], [0], color=TANGERINE, marker='*', markersize=12, linestyle='None',
           markeredgecolor='black', markeredgewidth=0.5, label="Cluster medoid tract"),
    Line2D([0], [0], color='black', markersize=10, linestyle='-',
           label='Outline of the original cluster'),
]
fig_key, (ax_cbar, ax_leg) = plt.subplots(1, 2, figsize=(10, 0.25),
                                           gridspec_kw={'width_ratios': [3, 2]})
cb = plt.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap),
                  cax=ax_cbar, orientation='horizontal')
cb.ax.tick_params(labelsize=12)
ax_leg.axis('off')
ax_leg.legend(handles=_legend_handles, fontsize=12, frameon=False, ncol=2,
              loc='center left', handlelength=1.5)
fig_key.savefig(figure_dir / "choropleth_key.png", dpi=300, bbox_inches='tight')
plt.close(fig_key)
print(f"Saved {figure_dir / 'choropleth_key.png'}")

for (area_code, city_name, cluster), tract_selections in tracts.groupby(['area_code', 'city_name', 'cluster'], sort=True):
    print(f"Plotting {city_name}, {cluster}")
    tracts_buf = tract_selections[tract_selections['buffer_size'] == DISPLAY_BUFFER]
    cluster_metrics = metrics[(metrics['area_code'] == area_code) & (metrics['cluster'] == cluster)]
    years = sorted(cluster_metrics['year'].unique())

    # pre-pass: compute radial data for all years so rmax can be shared across panels
    radial_by_year = {}
    for year in years:
        year_tracts = tracts_buf[tracts_buf['year'] == year]
        med_row = cluster_metrics[(cluster_metrics['year'] == year)
                                & (cluster_metrics['buffer_size'] == 0)]
        if med_row.empty or year_tracts.empty:
            continue
        rd = get_radial_data(area_code, year, year_tracts, med_row.iloc[0]['center_gisjoin'])
        if rd is not None:
            radial_by_year[year] = rd

    rmax = max(rd['reach'] for rd in radial_by_year.values()) if radial_by_year else 1

    fig_width = 4 * len(years)  # shared width across all three figures

    # figure 1: choropleth
    fig_choro, axes = plt.subplots(1, len(years), figsize=(fig_width, 4.5))
    if len(years) == 1:
        axes = [axes]

    for ax, year in zip(axes, years):
        year_selections = tracts_buf[tracts_buf['year'] == year]
        med_row = cluster_metrics[(cluster_metrics['year'] == year)
                                & (cluster_metrics['buffer_size'] == 0)]
        if med_row.empty:
            ax.axis('off')
            continue
        medoid_gisjoin = med_row.iloc[0]['center_gisjoin']

        geo_path = GEO_DIR / str(year) / f'tracts_in_max_city_{area_code}_{year}_march_2020_vintage.gpkg'
        gdf = gpd.read_file(geo_path)
        cluster_gdf = gdf.merge(year_selections[['gisjoin', 'black_share']],
                                left_on='GISJOIN', right_on='gisjoin', how='inner')
        cluster_gdf['choropleth_color'] = cluster_gdf['black_share'].apply(lambda x: cmap(norm(x)))
        cluster_gdf.plot(ax=ax, color=cluster_gdf['choropleth_color'].tolist(),
                         edgecolor='grey', linewidth=0.4)

        buf0_tracts = tract_selections[(tract_selections['year'] == year)
                                       & (tract_selections['buffer_size'] == 0)]
        buf0_gdf = gdf.merge(buf0_tracts[['gisjoin']], left_on='GISJOIN', right_on='gisjoin', how='inner')
        union = buf0_gdf.geometry.union_all()
        # fill interior holes by keeping only exterior rings
        if union.geom_type == 'Polygon':
            filled = Polygon(union.exterior)
        elif union.geom_type == 'MultiPolygon':
            filled = MultiPolygon([Polygon(p.exterior) for p in union.geoms])
        else:
            filled = union
        gpd.GeoSeries([filled], crs=gdf.crs).boundary.plot(
            ax=ax, color='black', linewidth=1.5, zorder=4)

        medoid_geom = gdf.loc[gdf['GISJOIN'] == medoid_gisjoin, 'geometry']
        if not medoid_geom.empty:
            c = medoid_geom.iloc[0].centroid
            ax.scatter(c.x, c.y, marker='*', s=100, color=TANGERINE,
                       linewidth=0.5, edgecolors='black', zorder=5)

        # ax.set_title(str(year), fontsize=20)
        ax.set_aspect('equal', adjustable='datalim')
        ax.axis('off')

    choro_path = figure_dir / f"{city_name}_{cluster}_choropleth.png"
    fig_choro.savefig(choro_path, dpi=300, bbox_inches='tight')
    plt.close(fig_choro)
    print(f"Saved {choro_path}")

    # figure 2: radial
    fig_radial, rad_axes = plt.subplots(1, len(years), figsize=(fig_width, 4.5))
    if len(years) == 1:
        rad_axes = [rad_axes]

    for ax, year in zip(rad_axes, years):
        if year not in radial_by_year:
            ax.axis('off')
            continue
        rd = radial_by_year[year]
        panel_radial(ax, rd['coords'], rd['share'], rmax, rd['reach'],
                      title="") #str(year)

    radial_path = figure_dir / f"{city_name}_{cluster}_radial.png"
    fig_radial.savefig(radial_path, dpi=300, bbox_inches='tight')
    plt.close(fig_radial)
    print(f"Saved {radial_path}")

    # figure 3: line plot
    fig_line, ax_line = plt.subplots(figsize=(fig_width, 3))

    buffer_size = 3
    sub = cluster_metrics[cluster_metrics['buffer_size'] == buffer_size].sort_values('year')
    ax_line.plot(sub['year'], sub['moran'], color=BLUE,
                    marker='o', markersize=4, linewidth=2)

    ax_line2 = ax_line.twinx()
    ax_line2.plot(sub['year'], sub['half_edge'], color=TANGERINE,
                marker='o', markersize=4, linewidth=2, alpha=0.8)
    ax_line2.set_ylabel("Capy", fontsize=25, color=TANGERINE, labelpad=-30)

    ax_line.set_ylabel("Moran's I", fontsize=25, color=BLUE, labelpad=-30)

    ax_line.set_yticks([sub['moran'].min(), sub['moran'].max()],
                       labels=[f"{sub['moran'].min():.2f}", f"{sub['moran'].max():.2f}"], fontsize=20)
    ax_line2.set_yticks([sub['half_edge'].min(), sub['half_edge'].max()],
                        labels=[f"{sub['half_edge'].min():.2f}", f"{sub['half_edge'].max():.2f}"], fontsize=20)
    ax_line.tick_params(axis='y', colors=BLUE, size=2)
    ax_line2.tick_params(axis='y', colors=TANGERINE, size=2)

    ax_line.set_xlim(years[0] - 3, years[-1] + 3)
    ax_line.set_xticks(years)
    ax_line.set_xticklabels([], fontsize=20)
    # ax_line.set_xticklabels([str(y) for y in years], fontsize=20)
    ax_line.tick_params(axis='x', pad=15)

    ax_line2.spines[['top', 'bottom', 'left', 'right']].set_edgecolor(RADIAL_BASELINE)

    lines_path = figure_dir / f"{city_name}_{cluster}_lines.png"
    fig_line.savefig(lines_path, dpi=300, bbox_inches='tight')
    plt.close(fig_line)
    print(f"Saved {lines_path}")
