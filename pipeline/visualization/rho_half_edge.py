"""Scatter plot of ρ (POC share of POC+White) vs Half Edge (λ=1) across U.S. metros."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib.colors as mcolors
import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pipeline.process_results import enrich_metrics

CSV = Path("outputs/tracts_in_cbsa/white_poc.csv")
OUT = Path("outputs/tracts_in_cbsa/figures/rho_vs_half_edge.png")

# ── data ──────────────────────────────────────────────────────────────────────
df = enrich_metrics(pd.read_csv(CSV))
# ρ = POC / (POC + White) — the minority share entering the Half Edge formula
df["rho"] = df["total_x"] / (df["total_x"] + df["total_y"])

# ── palette ───────────────────────────────────────────────────────────────────
BG          = "#fcfcfb"
PRIMARY_INK = "#0b0b0b"
SECONDARY   = "#52514e"
MUTED       = "#898781"
GRID        = "#e1e0d9"

# Blue→orange: sample RdYlBu_r, skipping the light yellow center (~0.35–0.60)
YEARS = sorted(df["year"].unique())
_cmap = plt.colormaps["RdYlBu_r"]
_positions = [0.0, 0.18, 0.30, 0.72, 0.88]
YEAR_COLORS = {
    year: mcolors.to_hex(_cmap(p))
    for year, p in zip(YEARS, _positions)
}

# ── theoretical star-bipartite limits ────────────────────────────────────────
# Minority hub, N→∞ white leaves: ⟨X,X⟩→0, skew'_self→0  →  H = ρ/2
# White hub,    N→∞ POC leaves:   ⟨X,X⟩→0, skew'_self→0,
#                                  skew'_other=(1−ρ)        →  H = (1−ρ)/2
rho_grid = np.linspace(0.001, 0.999, 800)
h_star_poc_hub   = rho_grid / 2

# ── empirical lower envelope (5th-percentile in ρ bins) ──────────────────────
bins = np.linspace(0, 1, 26)
bin_mid, p05 = [], []
for lo, hi in zip(bins[:-1], bins[1:]):
    mask = (df["rho"] >= lo) & (df["rho"] < hi)
    if mask.sum() >= 5:
        bin_mid.append((lo + hi) / 2)
        p05.append(df.loc[mask, "half_edge_1"].quantile(0.05))

# ── figure ────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(7.5, 6), facecolor=BG)
ax.set_facecolor(BG)
ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
ax.grid(color=GRID, linewidth=0.8, zorder=0)
ax.tick_params(length=0, labelsize=8, labelcolor=SECONDARY)

# scatter — each year a sequential blue shade; alpha for overlap
for year in YEARS:
    sub = df[df["year"] == year]
    ax.scatter(
        sub["rho"], sub["half_edge_1"],
        s=16, alpha=0.50, linewidths=0,
        color=YEAR_COLORS[year], zorder=2,
    )

# empirical minimum across all CBSA-year observations
h_min = df["half_edge_1"].min()
ax.axhline(h_min, color=MUTED, linewidth=1.4, linestyle="--", zorder=3)

# empirical 5th-percentile envelope
ax.plot(bin_mid, p05, color="#52514e", linewidth=1.6, linestyle="-",
        zorder=4, label="5th-pct lower envelope")

# ── axes labels ───────────────────────────────────────────────────────────────
ax.set_xlabel("ρ  (POC share of POC + White)", fontsize=10,
              color=SECONDARY, labelpad=6)
ax.set_ylabel("Half Edge  (λ = 1)", fontsize=10, color=SECONDARY, labelpad=6)
ax.set_xlim(-0.02, 1.02)

# ── title ─────────────────────────────────────────────────────────────────────
ax.set_title("ρ vs Half Edge across U.S. CBSAs",
             fontsize=12, fontweight="bold", color=PRIMARY_INK, pad=14)
ax.text(0.5, 1.01,
        "Census tracts · White–POC · 1980–2020",
        transform=ax.transAxes, ha="center", fontsize=8.5, color=MUTED)

# ── legend ────────────────────────────────────────────────────────────────────
year_handles = [
    mlines.Line2D([], [], color=YEAR_COLORS[y], marker="o",
                  linestyle="None", markersize=6, label=str(y))
    for y in YEARS
]
ref_handles = [
    mlines.Line2D([], [], color=MUTED, linewidth=1.4, linestyle="--",
                  label=f"Data minimum  (H = {h_min:.3f})"),
    mlines.Line2D([], [], color="#52514e", linewidth=1.6, linestyle="-",
                  label="5th-pct lower envelope"),
]
ax.legend(
    handles=year_handles + ref_handles,
    loc="upper right", frameon=True, framealpha=0.92,
    edgecolor=GRID, fontsize=8, labelcolor=SECONDARY,
    handlelength=1.8, handletextpad=0.6, labelspacing=0.4,
)

# ── save ──────────────────────────────────────────────────────────────────────
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close(fig)
print(f"Saved → {OUT}")
