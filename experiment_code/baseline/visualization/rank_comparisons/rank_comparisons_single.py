"""Pairwise rank comparison scatterplots — one figure per metric pair.

For each pair of metrics (Capy / Half Edge, Dissimilarity, Moran's I), plots the
top 100 cities (by population) in a given year by their within-group score ranks
against each other, with a linear regression line and R² annotation.

Saves one PNG per pair to:
    figures/baseline/<node_areas>_in_<study_areas>/rank_comparisons/<stem>_rank_<x>_vs_<y>.png

Usage (run from the project root):
    python experiment_code/baseline/visualization/rank_comparisons/rank_comparisons_single.py
"""

import re
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # experiment_code/baseline/

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from visualization.visualization_settings import PALETTE

# ── configuration ─────────────────────────────────────────────────────────────

CSV = Path("data/shared/outputs/tracts_in_cbsa/white_black.csv")

METRICS = {
    "half_edge_1": "Half Edge",
    "dissimilarity_1": "Dissimilarity",
    "moran_P": "Moran's I",
    "filename": "filename",
    "total_population": "total_population",
}
DISPLAY_METRICS = {
    "half_edge_1": "Capy Rank",
    "dissimilarity_1": "Dissimilarity Rank",
    "moran_P": "Moran's I Rank",
}

SELECTED_YEAR = "2020"
TOP_N = 100

# ── derived labels ─────────────────────────────────────────────────────────────

stem = CSV.stem  # e.g. "white_black"
if stem == "white_black":
    groups_compared = "White and Black"
else:
    groups_compared = "White and POC"

node_areas = re.search(r"outputs/([^_]+)_in", str(CSV)).group(1)   # e.g. "tracts"
study_areas_key = re.search(r"outputs/[^/]+_in_([^/]+)/", str(CSV)).group(1)  # e.g. "cbsa"
study_areas = (
    "the largest city per metropolitan area"
    if study_areas_key == "max_city"
    else study_areas_key
)

# ── load & prep ────────────────────────────────────────────────────────────────

df = pd.read_csv(CSV, usecols=list(METRICS))
df["year"] = df["filename"].str.extract(r"(\d{4})")
df = df.dropna(subset=list(METRICS))
df = df[df["year"] == SELECTED_YEAR]
df = df.sort_values("total_population", ascending=False).head(TOP_N)

for col in DISPLAY_METRICS:
    df[col + "_rank"] = df[col].rank(method="average")

# ── style ──────────────────────────────────────────────────────────────────────

BG = "#fcfcfb"
SECONDARY = "#52514e"
GRID = "#e1e0d9"
colors = PALETTE

# ── output dir ────────────────────────────────────────────────────────────────

out_dir = (
    Path("figures")
    / "baseline"
    / f"{node_areas}_in_{study_areas_key}"
    / "rank_comparisons"
)
out_dir.mkdir(parents=True, exist_ok=True)

# ── one figure per metric pair ────────────────────────────────────────────────

pairs = list(combinations(DISPLAY_METRICS.keys(), 2))  # 3 pairs

for x_col, y_col in pairs:
    fig, ax = plt.subplots(figsize=(5, 5), facecolor=BG)
    ax.set_facecolor(BG)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.grid(color=GRID, linewidth=0.8, zorder=0)
    ax.tick_params(length=0, labelsize=8, labelcolor=SECONDARY)
    ax.set_box_aspect(1)

    x = df[x_col + "_rank"]
    y = df[y_col + "_rank"]

    ax.scatter(x, y, s=18, alpha=1, color=colors[0], linewidths=0, zorder=2)

    m, b = np.polyfit(x, y, 1)
    r2 = np.corrcoef(x, y)[0, 1] ** 2
    x_line = np.linspace(x.min(), x.max(), 100)
    ax.plot(x_line, m * x_line + b, color=SECONDARY, lw=1, alpha=0.7)
    ax.annotate(
        f"$R^2={r2:.2f}$",
        xy=(0.05, 0.92),
        xycoords="axes fraction",
        fontsize=8,
        color=SECONDARY,
    )

    ax.set_xlabel(DISPLAY_METRICS[x_col], fontsize=9, color=SECONDARY, labelpad=6)
    ax.set_ylabel(DISPLAY_METRICS[y_col], fontsize=9, color=SECONDARY, labelpad=6)

    out_path = out_dir / f"{stem}_rank_{x_col}_vs_{y_col}.png"
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"Saved → {out_path}")
