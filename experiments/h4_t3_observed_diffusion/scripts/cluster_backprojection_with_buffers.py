import json
import networkx as nx
import pandas as pd
import geopandas as gpd
# from networkx.readwrite import json_graph
from shapely.geometry import Polygon
from shapely.ops import unary_union

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent # to capy-bara/
# sys.path.insert(0, str(ROOT)) # for pipeline.*
sys.path.insert(0, str(ROOT / "experiments" / "h4_t3_observed_diffusion")) # for utils.*

# from pipeline.metrics import moran, dissimilarity, half_edge
from utils.cluster_helpers import compute_rho, get_geoids, back_project_cluster, apply_metrics_to_cities


# Config
CBSA_CONFIG = {
    "1714000": {"name": "Chicago"},
    "4260000": {"name": "Philadelphia"}}
    # "1245000": {"name": "Miami"}}
CBSA = "1714000"

OVERLAP_THRESHOLD = 0.50
YEARS = [1980, 1990, 2000, 2010, 2020]
N_EDGES = 2 # buffer size

DUAL_GRAPHS_DIR = ROOT / "data" / "processed" / "dual_graphs"
CLIPPED_GEO_DIR = ROOT / "data" / "processed" / "clipped_geographies"
OUTPUT_JSON_FILES = ROOT / "experiments" / "h4_t3_observed_diffusion" / "data" / "cluster_graphs_buffers"
OUTPUT_NODE_LIST = ROOT / "experiments" / "h4_t3_observed_diffusion" / "data" / "auto_cluster_tracts.csv"



for CBSA in CBSA_CONFIG.keys():
    print(f'--------- Working on area ID = {CBSA} ---------')
    graph_file = DUAL_GRAPHS_DIR / "2020" / f"tracts_in_max_city_{CBSA}_2020_march_2020_vintage_connected.json"
    with open(graph_file) as f:
        G_city_2020 = nx.adjacency_graph(json.load(f))
    BLACK_SHARE_THRESHOLD = compute_rho(G_city_2020)

    node_ids = list(G_city_2020.nodes())
    nodes_df = pd.DataFrame([G_city_2020.nodes[n] for n in node_ids], index=node_ids)
    nodes_df["black_share"] = nodes_df["BLACK"] / (nodes_df["BLACK"] + nodes_df["WHITE"])
    nodes_df["majority_black"] = nodes_df["black_share"] > BLACK_SHARE_THRESHOLD

    print(f"Total tracts: {len(nodes_df)}")
    print(f"Majority-Black (>{BLACK_SHARE_THRESHOLD:.0%}): {nodes_df['majority_black'].sum()}")
    print(f"Below threshold: {(~nodes_df['majority_black']).sum()}")
    print(f'Rho of area:', BLACK_SHARE_THRESHOLD)

    majority_black_nodes = set(nodes_df.index[nodes_df["majority_black"]])

    # pick 2 largest connected components
    G_city_2020_subgraphs = G_city_2020.subgraph(majority_black_nodes)
    ccomponents = sorted(nx.connected_components(G_city_2020_subgraphs), key=len, reverse=True)[:2]
    cluster_node_ids = {"cluster_1": ccomponents[0], "cluster_2": ccomponents[1]}

    # add buffers to them
    buffered_node_ids = {}
    for label, nodes in cluster_node_ids.items():
        expanded = set(nodes)
        for step in range(N_EDGES):
            expanded.update(nb for n in list(expanded) for nb in G_city_2020.neighbors(n))
        buffered_node_ids[label] = expanded

    #### Connect the selected nodes to their polygons: polygons are needed to fill any holes among selected nodes and to match tracts back in time, since they don't match well by IDs due to mergers and splits taking place between the decades.
    gpkg_2020 = CLIPPED_GEO_DIR / "2020" / f"tracts_in_max_city_{CBSA}_2020_march_2020_vintage.gpkg"
    gdf_2020 = gpd.read_file(gpkg_2020)

    # Map graph node ids to GEOIDs to gpkg rows
    cluster_geoids = {label: set(nodes_df.loc[nodes_df.index.isin(ids), "GEOID"].astype(str))
        for label, ids in buffered_node_ids.items()}

    # Filter gdf rows by those GEOIDs
    cluster_gdfs_2020 = {}
    for label, geoids in cluster_geoids.items():
        gdf = gdf_2020[gdf_2020["GEOID"].astype(str).isin(geoids)].copy()
        gdf["cluster"] = label
        cluster_gdfs_2020[label] = gdf
        print(f"2020 {label}: {len(gdf)} tracts matched in gpkg (of {len(geoids)} graph nodes)")

    # Fill holes
    cluster_shapes_2020 = {}
    for label, gdf in cluster_gdfs_2020.items():
        dissolved = gdf.dissolve().geometry.iloc[0]
        # Fill holes in each piece, keeping all disconnected parts
        if dissolved.geom_type == "Polygon":
            filled = Polygon(dissolved.exterior)
        else:  # MultiPolygon - buffer created from spatially disconnected pieces
            filled = unary_union([Polygon(p.exterior) for p in dissolved.geoms])
        cluster_shapes_2020[label] = gpd.GeoDataFrame(geometry=[filled], crs=gdf.crs)


    #### Apply to previous years
    # For each earlier-year tract: if `intersection_area / tract_area > OVERLAP_THRESHOLD`, it belongs to the cluster.
    cluster_yearly = {2020: cluster_gdfs_2020}
    graph_yearly = {}

    for year in YEARS:
        gpkg_path = CLIPPED_GEO_DIR / str(year) / f"tracts_in_max_city_{CBSA}_{year}_march_2020_vintage.gpkg"
        gdf_year = gpd.read_file(gpkg_path)
        cluster_yearly[year] = {}
        for label, gdf_cluster in cluster_shapes_2020.items():
            matched = back_project_cluster(gdf_cluster, gdf_year, OVERLAP_THRESHOLD)
            matched = matched.copy()
            matched["cluster"] = label
            cluster_yearly[year][label] = matched

        graph_file = DUAL_GRAPHS_DIR / str(year) / f"tracts_in_max_city_{CBSA}_{year}_march_2020_vintage_connected.json"
        with open(graph_file) as f:
            G_year = nx.adjacency_graph(json.load(f))

        # GEOID to node-id index for this year's graph
        geoid_to_node = {str(attrs["GEOID"]): n for n, attrs in G_year.nodes(data=True)}

        graph_yearly[year] = {}
        for label, gdf in cluster_yearly[year].items():
            geoids = get_geoids(gdf)
            # select the cluster GEOIDs in the json file: 
            nodes = [geoid_to_node[g] for g in geoids if g in geoid_to_node]
            graph_yearly[year][label] = G_year.subgraph(nodes).copy()

    metrics_by_year = {}
    for year in YEARS:
        for label in cluster_node_ids:
            metrics_by_year = apply_metrics_to_cities(G=graph_yearly[year][label], year=year, label=label,
                metrics_by_year=metrics_by_year)

    #### Save two outputs:
    # 1) save json files, a file per graph
    print(f"Saving graphs as json files to {OUTPUT_JSON_FILES}")
    for year, clusters in graph_yearly.items():
        for label, G in clusters.items():
            out = OUTPUT_JSON_FILES / f"{CBSA}_{year}_{label}.json"
            with open(out, "w") as f:
                json.dump(nx.adjacency_data(G), f)

    # 2) alternatively and better for further calculations, save gisjoin ids
    rows = []
    for year, clusters in graph_yearly.items():
        for label, G in clusters.items():
            for n, attrs in G.nodes(data=True):
                rows.append({"area_code": CBSA, "year": year, "cluster": label, "gisjoin": attrs["GISJOIN"]})
    print(f"Saving list of selected nodes to {OUTPUT_NODE_LIST}")
    pd.DataFrame(rows).to_csv(OUTPUT_NODE_LIST, index=False)
