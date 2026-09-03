"""Like rho_vs_metrics_panel.py but saves one file per metric."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib.lines as mlines
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from pipeline.process_results import enrich_metrics
from pipeline.utils.visualization_settings import PALETTE

# path_to_file = "outputs/tracts_in_cbsa/white_poc.csv"
path_to_file = "outputs/tracts_in_cbsa/white_black.csv"
CSV = Path(path_to_file)

# ── data ──────────────────────────────────────────────────────────────────────
df = enrich_metrics(pd.read_csv(CSV))
if "white_poc" in path_to_file:
    df["rho"] = df["total_poc"] / (df["total_poc"] + df["total_white"])
    prefix = "wpoc"
    print('White-POC metrics')
elif "white_black" in path_to_file:
    df["rho"] = df["total_black"] / (df["total_black"] + df["total_white"])
    prefix = "wb"
    print('White-Black metrics')
else:
    raise ValueError("Unknown file")

# ── palette ───────────────────────────────────────────────────────────────────
BG = "#fcfcfb"
PRIMARY_INK = "#0b0b0b"
SECONDARY = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"

YEARS = sorted(df["year"].unique())
YEAR_COLORS = {1980: '#1560bd',
               1990: '#006b3c',
               2000: "#8db600",
               2010: "#ffa812",
               2020: "#d11a42"}

# ── filter: CBSAs present in all 5 decades with population > 100K ────────────
df["area_code"] = df["filename"].str.extract(r"tracts_in_cbsa_(\d+)_")

ALL_YEARS = {1980, 1990, 2000, 2010, 2020}
cbsas_all_years = (df.groupby("area_code")["year"]
    .apply(lambda s: ALL_YEARS.issubset(set(s)))
    .pipe(lambda x: x[x].index))
min_pop = df.groupby("area_code")["total_population"].min()
cbsas_large = min_pop[min_pop > 100_000].index

valid_cbsas = cbsas_all_years.intersection(cbsas_large)
df = df[df["area_code"].isin(valid_cbsas)]
n_cbsas = len(valid_cbsas)

# ── panels definition ─────────────────────────────────────────────────────────
PANELS = [
    dict(col="half_edge_1", title="Capy",
         range_label="Range: 0 (checkerboard) to 1 (perfect segregation)",
         hline_y=0.5, hline_label="Uniform distribution (Capy = 0.5)"),
    dict(col="moran_P", title="Moran's I",
         range_label="Range: −1 (checkerboard) to 1 (perfect segregation)",
         hline_y=0.0, hline_label="No spatial autocorrelation (I = 0)"),
    dict(col="dissimilarity_1", title="Dissimilarity",
         range_label="Range: 0 (uniform) to 1 (fully segregated)",
         hline_y=None, hline_label=None),
]

OUT_DIR = Path("outputs/tracts_in_cbsa/figures/rho_vs_metrics")
OUT_DIR.mkdir(parents=True, exist_ok=True)

year_handles = [mlines.Line2D([], [], color=YEAR_COLORS[y], marker="o",
                  linestyle="-", linewidth=1.2, markersize=6, label=str(y))
    for y in YEARS]
fit_handle = mlines.Line2D([], [], color=SECONDARY, linestyle="-", linewidth=1.2,
                            label="linear fit per decade")

# ── one figure per metric ─────────────────────────────────────────────────────
for panel in PANELS:
    col = panel["col"]

    fig, ax = plt.subplots(figsize=(7, 6.8), facecolor=BG)
    ax.set_facecolor(BG)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.grid(color=GRID, linewidth=0.8, zorder=0)
    ax.tick_params(length=0, labelsize=8, labelcolor=SECONDARY)

    for year in YEARS:
        sub = df[df["year"] == year].dropna(subset=["rho", col])
        ax.scatter(sub["rho"], sub[col], s=16, alpha=0.50, linewidths=0,
            color=YEAR_COLORS[year], zorder=2)
        coeffs = np.polyfit(sub["rho"], sub[col], 1)
        x_fit = np.linspace(sub["rho"].min(), sub["rho"].max(), 300)
        ax.plot(x_fit, np.polyval(coeffs, x_fit),
                color=YEAR_COLORS[year], linewidth=1.2, alpha=0.85, zorder=3)

    ref_handles = []
    if panel["hline_y"] is not None:
        ax.axhline(panel["hline_y"], color=MUTED, linewidth=1.1, zorder=4)
        ref_handles.append(mlines.Line2D([], [], color=MUTED, linewidth=1.2,
                           label=panel["hline_label"]))

    col_min = df[col].min()
    ax.axhline(col_min, color=PRIMARY_INK, linewidth=1.2, linestyle="--", zorder=3)
    ref_handles.append(mlines.Line2D([], [], color=PRIMARY_INK, linewidth=1.4,
                       linestyle="--", label=f"Data min ({col_min:.2f})"))

    ax.legend(handles=ref_handles, loc="upper right", frameon=True,
              framealpha=0.92, edgecolor=GRID, fontsize=7.5,
              labelcolor=SECONDARY, handlelength=1.6,
              handletextpad=0.5, labelspacing=0.3)

    ax.set_xlabel("Minority share", fontsize=10, color=SECONDARY, labelpad=6)
    ax.set_ylabel(panel["title"], fontsize=10, color=SECONDARY, labelpad=6)
    ax.text(0.5, 1.02, panel["range_label"], transform=ax.transAxes,
            ha="center", va="bottom", fontsize=7.5, color=MUTED)

    fig.legend(handles=year_handles + [fit_handle],
        loc="lower center", bbox_to_anchor=(0.5, -0.07),
        fontsize=9, frameon=False, ncol=6, labelcolor=SECONDARY, handletextpad=0.4)

    out = OUT_DIR / f"{prefix}_{col}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"Saved → {out}")
