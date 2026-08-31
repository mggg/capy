"""Choropleth map of U.S. CBSAs coloured by Half Edge (λ=1), 2020."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import geopandas as gpd
import pandas as pd

from pipeline.process_results import enrich_metrics
from pipeline.utils.visualization_settings import GRID_METRICS

# ── configuration 
YEAR = 2020  # census decade: 1980 | 1990 | 2000 | 2010 | 2020
METRIC = "moran_P" # column from white_poc.csv. options:
# "half_edge_1" - HE
# "moran_P" - Moran's I (row-standardised)
# "dissimilarity_1" - Dissimilarity
VMIN = 0.5 # colour-scale lower bound; None → use data minimum

CSV          = Path("outputs/tracts_in_cbsa/white_poc.csv")
GEO_DIR      = Path(f"data/processed/clipped_geographies/{YEAR}")
OUT          = Path(f"outputs/tracts_in_cbsa/figures/cbsa_{METRIC}_map_{YEAR}.png")
STATES_CACHE = Path("data/processed/us_states_20m.gpkg")

ALBERS = "EPSG:5070"   # Albers Equal Area Conic — standard for CONUS choropleth

# FIPS codes to exclude so the map stays on CONUS (Alaska, Hawaii, territories)
_NON_CONUS = {"02", "15", "60", "66", "69", "72", "78"}

# human-readable label for the chosen metric
METRIC_LABEL = GRID_METRICS.get(METRIC, METRIC)

# ── style ─────────────────────────────────────────────────────────────────────
BG          = "#fcfcfb"
PRIMARY_INK = "#0b0b0b"
SECONDARY   = "#52514e"
MUTED       = "#898781"

# ── data: one Half Edge value per CBSA in 2020 ────────────────────────────────
df = enrich_metrics(pd.read_csv(CSV))
df["area_code"] = df["filename"].str.extract(r"tracts_in_cbsa_(\d+)_")
df2020 = (df[df["year"] == YEAR]
          .groupby("area_code", as_index=False)[METRIC]
          .first()
          .dropna())

# ── geometry: dissolve each CBSA's tracts into one polygon ────────────────────
crs = None
records = []
n = len(df2020)
for i, (_, row) in enumerate(df2020.iterrows(), 1):
    code = row["area_code"]
    path = GEO_DIR / f"tracts_in_cbsa_{code}_{YEAR}_march_2020_vintage.gpkg"
    if not path.exists():
        continue
    try:
        gdf = gpd.read_file(path)
    except Exception as e:
        print(f"  [{i}/{n}] skip {code}: {e}")
        continue
    if crs is None:
        crs = gdf.crs
    records.append({
        "area_code": code,
        METRIC:      row[METRIC],
        "geometry":  gdf.geometry.union_all(),
    })
    if i % 50 == 0:
        print(f"  {i}/{n} loaded")

print(f"Dissolved {len(records)} CBSAs")
cbsa_gdf = gpd.GeoDataFrame(records, crs=crs).to_crs(ALBERS)

# ── state boundaries (download once, cache locally) ───────────────────────────
if not STATES_CACHE.exists():
    print("Downloading state boundaries from Census Bureau (one-time)...")
    _url = "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_state_20m.zip"
    _states_raw = gpd.read_file(_url)
    STATES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _states_raw.to_file(STATES_CACHE, driver="GPKG")
    print(f"  Cached → {STATES_CACHE}")
states_gdf = (gpd.read_file(STATES_CACHE)
              .query("STATEFP not in @_NON_CONUS")
              .to_crs(ALBERS))

# ── colour scale: anchor at 0.5 (uniform-distribution baseline) ───────────────
# Values below 0.5 are theoretically possible (checkerboard) but rare in practice;
# pin vmin at 0.5 so the colour ramp reads as distance from the uniform baseline.
vmin = cbsa_gdf[METRIC].min() if VMIN is None else VMIN
vmax = cbsa_gdf[METRIC].quantile(0.99)   # trim extreme outliers
cmap = "YlOrRd"                           # light = low; dark = high
norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

# ── figure ────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(14, 9), facecolor=BG)
ax.set_facecolor(BG)
ax.axis("off")

# state outlines as context — drawn first so CBSAs sit on top
states_gdf.plot(ax=ax, facecolor="#ebebea", edgecolor="#c0bfb8",
                linewidth=0.5, zorder=1)

# set axes extent from CONUS states so Alaska/Hawaii CBSAs don't warp the frame
xlim = (states_gdf.total_bounds[0], states_gdf.total_bounds[2])
ylim = (states_gdf.total_bounds[1], states_gdf.total_bounds[3])
ax.set_xlim(xlim)
ax.set_ylim(ylim)

cbsa_gdf.plot(
    ax=ax, column=METRIC, cmap=cmap, norm=norm,
    edgecolor="white", linewidth=0.25, zorder=2,
)

# colorbar
sm   = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
cbar = fig.colorbar(sm, ax=ax, fraction=0.018, pad=0.01,
                    shrink=0.55, orientation="vertical")
cbar.set_label(METRIC_LABEL, fontsize=9, color=SECONDARY, labelpad=8)
cbar.ax.tick_params(labelsize=8, labelcolor=SECONDARY)
cbar.ax.spines[:].set_visible(False)

# mark VMIN on the colorbar when it's a meaningful theoretical threshold
if VMIN is not None and vmin <= VMIN <= vmax:
    _t = (VMIN - vmin) / (vmax - vmin)
    cbar.ax.axhline(_t, color=PRIMARY_INK, linewidth=1.0, linestyle="--")
    cbar.ax.text(1.6, _t, f"{VMIN} (baseline)", va="center", fontsize=7,
                 color=PRIMARY_INK, transform=cbar.ax.transAxes)

# title
ax.set_title(f"{METRIC_LABEL} across U.S. CBSAs, {YEAR}",
             fontsize=14, fontweight="bold", color=PRIMARY_INK, pad=14)
ax.text(0.5, -0.01,
        f"White–POC {METRIC_LABEL}. CBSA footprints dissolved from {YEAR} tract boundaries.",
        transform=ax.transAxes, ha="center", fontsize=8.5, color=MUTED)

# ── save ──────────────────────────────────────────────────────────────────────
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close(fig)
print(f"Saved → {OUT}")
