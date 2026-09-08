"""
Cluster Definition and Back-Projection

For a given CBSA:
1. Load the 2020 dual graph; find the 2 largest connected components of majority-Black tracts
2. Map graph nodes to 2020 polygon geometries; dissolve and fill holes
3. Back-project both clusters to 1980–2020 via areal overlap (>50% of each earlier-year tract)
4. Check graph connectivity of the back-projected tracts in the earlier-year dual graphs
5. Save all-years cluster membership to CSV
"""

import json
from pathlib import Path
from shapely.ops import unary_union
from shapely.geometry import Polygon
import networkx as nx
import pandas as pd
import geopandas as gpd

# ── Config ────────────────────────────────────────────────────────────────────

CBSA_CONFIG = {
    "1714000": {"name": "Chicago"},
    "4260000": {"name": "Philadelphia"},
    # "1245000": {"name": "Miami"}
    }

OVERLAP_THRESHOLD = 0.50  # earlier-year tract must have >50% area in cluster

YEARS = [1980, 1990, 2000, 2010, 2020]

ROOT = Path("/Users/maria/Documents/capy-bara")
DUAL_GRAPHS_DIR = ROOT / "data" / "processed" / "dual_graphs"
CLIPPED_GEO_DIR = ROOT / "data" / "processed" / "clipped_geographies"
OUTPUT_FILE = ROOT / "experiments" / "h4_t3_observed_diffusion" / "data" / "auto_cluster_tracts.csv"

CLUSTER_TITLES = {
    ("1714000", "cluster_1"): "Chicago, South Side",
    ("1714000", "cluster_2"): "Chicago, Austin",
    ("4260000", "cluster_1"): "Philadelphia, Germantown",
    ("4260000", "cluster_2"): "Philadelphia, Chester",
    ("1245000", "cluster_1"): "Miami, North-central Miami-Dade",
    # ("1245000", "cluster_2"): "Miami, Lauderhill–Lauderdale Lakes–N Lauderdale"
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def compute_threshold(G):
    """Black share of the whole graph: total BLACK / (total BLACK + total WHITE)."""
    total_black = sum(int(attrs["BLACK"]) for _, attrs in G.nodes(data=True))
    total_white = sum(int(attrs["WHITE"]) for _, attrs in G.nodes(data=True))
    return total_black / (total_black + total_white)


def load_graph(json_path):
    """Load a dual-graph JSON into a networkx Graph. Returns (G, node_df)."""
    with open(json_path) as f:
        data = json.load(f)
    G = nx.Graph()
    for node in data["nodes"]:
        G.add_node(node["id"], **node)
    for node_id, neighbors in enumerate(data["adjacency"]):
        for edge in neighbors:
            G.add_edge(node_id, edge["id"], shared_perim=edge["shared_perim"])
    return G, pd.DataFrame(data["nodes"])


def back_project_cluster(gdf_cluster, gdf_target, overlap_threshold=0.50):
    """
    Returns rows of gdf_target whose tract area overlaps > overlap_threshold
    with the dissolved cluster polygon.
    """
    if gdf_target.crs != gdf_cluster.crs:
        gdf_target = gdf_target.to_crs(gdf_cluster.crs)

    cluster_union = unary_union(gdf_cluster.geometry)

    target = gdf_target.copy()
    target["_tract_area"] = target.geometry.area
    target["_inter_area"] = target.geometry.intersection(cluster_union).area
    target["_overlap"] = target["_inter_area"] / target["_tract_area"]

    return (target[target["_overlap"] > overlap_threshold]
            .drop(columns=["_tract_area", "_inter_area", "_overlap"])
            .copy())


all_rows = []
all_connectivity_rows = []

for CBSA, cfg in CBSA_CONFIG.items():
    # ── Step 1 — 2020 dual graph: define majority-Black clusters ──────────────

    graph_file = DUAL_GRAPHS_DIR / "2020" / f"tracts_in_max_city_{CBSA}_2020_march_2020_vintage_orig.json"
    G_2020, _ = load_graph(graph_file)
    BLACK_SHARE_THRESHOLD = compute_threshold(G_2020)
    print(f"\n{'='*60}")
    print(f"CBSA {CBSA} ({cfg['name']})  threshold={BLACK_SHARE_THRESHOLD:.1%} (computed)")
    print('='*60)
    print(f"2020 graph: {G_2020.number_of_nodes()} nodes, {G_2020.number_of_edges()} edges")

    nodes_df = pd.DataFrame([G_2020.nodes[n] for n in G_2020.nodes()])
    nodes_df["black_share"] = (
        nodes_df["BLACK"] / (nodes_df["BLACK"] + nodes_df["WHITE"]).replace(0, pd.NA))
    nodes_df["majority_black"] = nodes_df["black_share"] > BLACK_SHARE_THRESHOLD

    print(f"Majority-Black (>{BLACK_SHARE_THRESHOLD:.0%}): {nodes_df['majority_black'].sum()} "
          f"/ {len(nodes_df)} tracts")

    majority_ids = set(nodes_df.loc[nodes_df["majority_black"], "id"])
    G_black = G_2020.subgraph(majority_ids)

    components = sorted(nx.connected_components(G_black), key=len, reverse=True)
    print(f"Connected components in majority-Black subgraph: {len(components)}")
    print(f"Sizes of top 5: {[len(c) for c in components[:5]]}")

    cluster_node_ids = {"cluster_1": components[0], "cluster_2": components[1]}

    # ── Step 2 — Map graph nodes to 2020 polygon geometries ──────────────────

    gpkg_2020 = CLIPPED_GEO_DIR / "2020" / f"tracts_in_max_city_{CBSA}_2020_march_2020_vintage.gpkg"
    gdf_2020 = gpd.read_file(gpkg_2020)

    cluster_geoids = {
        label: set(nodes_df.loc[nodes_df["id"].isin(ids), "GEOID"])
        for label, ids in cluster_node_ids.items()
    }

    cluster_gdfs_2020 = {}
    for label, geoids in cluster_geoids.items():
        gdf = gdf_2020[gdf_2020["GEOID"].isin(geoids)].copy()
        gdf["cluster"] = label
        cluster_gdfs_2020[label] = gdf
        print(f"2020 {label}: {len(gdf)} tracts matched in gpkg (of {len(geoids)} graph nodes)")

    # Dissolve and fill interior holes so back-projection captures enclosed tracts
    cluster_shapes_2020 = {}
    for label, gdf in cluster_gdfs_2020.items():
        dissolved = gdf.dissolve().geometry.iloc[0]
        dissolved = Polygon(dissolved.exterior)  # drop holes
        cluster_shapes_2020[label] = gpd.GeoDataFrame(geometry=[dissolved], crs=gdf.crs)

    # ── Step 3 — Back-project to all years via areal overlap ─────────────────

    cluster_yearly = {}
    for year in YEARS:
        gpkg_path = CLIPPED_GEO_DIR / str(year) / f"tracts_in_max_city_{CBSA}_{year}_march_2020_vintage.gpkg"
        gdf_year = gpd.read_file(gpkg_path)
        cluster_yearly[year] = {}

        for label, gdf_cluster in cluster_shapes_2020.items():
            matched = back_project_cluster(gdf_cluster, gdf_year, OVERLAP_THRESHOLD)
            matched = matched.copy()
            matched["cluster"] = label
            cluster_yearly[year][label] = matched
            print(f"{year} {label}: {len(matched)} tracts")

    # ── Step 4 — Graph connectivity check ────────────────────────────────────

    for year in YEARS:
        json_path = DUAL_GRAPHS_DIR / str(year) / f"tracts_in_max_city_{CBSA}_{year}_march_2020_vintage_orig.json"
        G_year, node_df_year = load_graph(json_path)

        for label in ["cluster_1", "cluster_2"]:
            gdf_matched = cluster_yearly[year][label]
            if len(gdf_matched) == 0:
                continue

            matched_geoids = set(gdf_matched["GEOID"])
            matched_node_ids = set(
                node_df_year.loc[node_df_year["GEOID"].isin(matched_geoids), "id"])
            unmatched = matched_geoids - set(node_df_year["GEOID"])

            G_sub = G_year.subgraph(matched_node_ids)
            comps = sorted(nx.connected_components(G_sub), key=len, reverse=True)

            all_connectivity_rows.append({
                "area_code": CBSA,
                "year": year,
                "cluster": label,
                "areal_overlap_tracts": len(matched_geoids),
                "in_graph": len(matched_node_ids),
                "not_in_graph": len(unmatched),
                "n_components": len(comps),
                "largest_component": len(comps[0]) if comps else 0,
            })

    # ── Step 5 — Collect rows for this CBSA ──────────────────────────────────

    for year, clusters in cluster_yearly.items():
        for label, gdf in clusters.items():
            if len(gdf) == 0:
                raise ValueError(f"Empty cluster: area_code={CBSA}, year={year}, label={label}")
            sub = gdf[["GEOID", "GISJOIN", "STATEFP", "COUNTYFP",
                       "BLACK", "WHITE", "POC", "TOTPOP"]].copy()
            sub["area_code"] = CBSA
            sub["year"] = year
            sub["cluster"] = label
            sub["black_share"] = sub["BLACK"] / (sub["BLACK"] + sub["WHITE"]).replace(0, pd.NA)
            all_rows.append(sub)


# ── Connectivity summary ──────────────────────────────────────────────────────

conn_df = pd.DataFrame(all_connectivity_rows)
print("\nConnectivity check:")
print(conn_df.to_string(index=False))


# ── Save combined CSV ─────────────────────────────────────────────────────────

df_out = (
    pd.concat(all_rows, ignore_index=True)
    .rename(columns={
        "BLACK": "black_population",
        "TOTPOP": "total_population",
        "WHITE": "white_population",
        "POC": "poc_population",
        "GEOID": "geoid",
        "GISJOIN": "gisjoin",
        "STATEFP": "statefp",
        "COUNTYFP": "countyfp",
    })
    [["area_code", "year", "cluster", "gisjoin", "geoid",
      "black_population", "total_population", "black_share"]]
    .sort_values(["area_code", "cluster", "year", "geoid"])
    .reset_index(drop=True)
)

df_out["cluster_title"] = df_out.apply(
    lambda r: CLUSTER_TITLES.get((r["area_code"], r["cluster"]), "Other"), axis=1)

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
df_out.to_csv(OUTPUT_FILE, index=False)
print(f"\nSaved {len(df_out)} rows to {OUTPUT_FILE}")
print(df_out.groupby(["area_code", "year", "cluster"]).size().unstack(["area_code", "cluster"]).to_string())
