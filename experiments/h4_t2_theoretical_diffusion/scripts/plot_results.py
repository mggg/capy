"""
H4 T2: Plot Half Edge and Moran trajectories from the diffusion simulation.

Produces two figures:
  1. trajectories.png  — absolute trajectories of HE, Moran, and Dissimilarity
                         per graph type; one panel per graph, lines per seed position.
  2. divergence.png    — Δ(Half Edge) and Δ(Moran) relative to step 0 on the same
                         normalized axis, making the divergence between the two
                         metrics explicit.

Run from the repo root:
    python experiments/h4_t2_theoretical_diffusion/scripts/plot_results.py
"""

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
INPUT   = EXPERIMENT_DIR / "data" / "diffusion_results.csv"
OUT_DIR = EXPERIMENT_DIR / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Palette ───────────────────────────────────────────────────────────────────
BG           = "#fcfcfb"
PRIMARY_INK  = "#0b0b0b"
SECONDARY    = "#52514e"
MUTED        = "#898781"
GRID_COLOR   = "#e1e0d9"

HE_COLOR     = "#1a5276"   # deep blue  — Half Edge
MORAN_COLOR  = "#b7410e"   # burnt orange — Moran
DISSIM_COLOR = "#6c6c6c"   # grey — Dissimilarity

# Seed-position line styles (up to 4)
LINE_STYLES  = ["-", "--", ":", "-."]
LINE_WEIGHTS = [2.0, 1.8, 1.8, 1.8]

GRAPH_LABELS = {
    "grid":        "Grid (12×12)",
    "ring":        "Ring (60 nodes)",
    "star":        "Star (30 leaves)",
    "barbell":     "Barbell (10+6+10)",
    "hex":         "Hexagonal lattice",
    "triangular":  "Triangular lattice",
}

# ── Load data ─────────────────────────────────────────────────────────────────
df = pd.read_csv(INPUT)
graph_types = list(GRAPH_LABELS.keys())
n_graphs = len(graph_types)


def _setup_ax(ax):
    ax.set_facecolor(BG)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID_COLOR)
    ax.tick_params(length=0, labelsize=7, labelcolor=SECONDARY)
    ax.grid(color=GRID_COLOR, linewidth=0.7, zorder=0)
    ax.xaxis.set_minor_locator(mticker.AutoMinorLocator(2))


# ── Figure 1: Absolute trajectories ───────────────────────────────────────────
ncols = 3
nrows = 2
fig1, axes1 = plt.subplots(
    nrows, ncols,
    figsize=(13, 8),
    facecolor=BG,
    constrained_layout=True,
)
axes1 = axes1.flatten()

for ax_idx, gtype in enumerate(graph_types):
    ax = axes1[ax_idx]
    _setup_ax(ax)

    sub = df[df["graph_type"] == gtype]
    positions = sub["seed_position"].unique()

    ax2 = ax.twinx()
    ax2.set_facecolor(BG)
    ax2.spines[["top", "left"]].set_visible(False)
    ax2.spines[["right", "bottom"]].set_color(GRID_COLOR)
    ax2.tick_params(length=0, labelsize=7, labelcolor=MORAN_COLOR)

    for pi, pos in enumerate(positions):
        ls = LINE_STYLES[pi % len(LINE_STYLES)]
        lw = LINE_WEIGHTS[pi % len(LINE_WEIGHTS)]
        posdf = sub[sub["seed_position"] == pos].sort_values("step")
        label = pos.replace("_", " ")

        ax.plot(posdf["step"], posdf["half_edge"],
                color=HE_COLOR, linestyle=ls, linewidth=lw, label=label, zorder=3)
        ax.plot(posdf["step"], posdf["dissimilarity"],
                color=DISSIM_COLOR, linestyle=ls, linewidth=1.2, alpha=0.6, zorder=2)
        ax2.plot(posdf["step"], posdf["moran"],
                 color=MORAN_COLOR, linestyle=ls, linewidth=lw, alpha=0.85, zorder=3)

    ax.set_xlabel("Diffusion step", fontsize=8, color=SECONDARY)
    ax.set_ylabel("Half Edge  (blue) / Dissimilarity (grey)", fontsize=7, color=HE_COLOR)
    ax2.set_ylabel("Moran's I", fontsize=7, color=MORAN_COLOR, rotation=-90, labelpad=12)

    ax.set_title(GRAPH_LABELS[gtype], fontsize=9, fontweight="bold",
                 color=PRIMARY_INK, pad=6)

    # Legend for line-style = seed position (first panel only for brevity)
    if ax_idx == 0:
        handles = [
            plt.Line2D([0], [0], color=HE_COLOR, lw=2, label="Half Edge (left)"),
            plt.Line2D([0], [0], color=MORAN_COLOR, lw=2, label="Moran's I (right)"),
            plt.Line2D([0], [0], color=DISSIM_COLOR, lw=1.5, alpha=0.7, label="Dissimilarity (left)"),
        ]
        ax.legend(handles=handles, fontsize=7, frameon=True,
                  framealpha=0.9, edgecolor=GRID_COLOR, loc="upper right",
                  labelcolor=SECONDARY)

    # Seed-position legend in every panel
    pos_handles = [
        plt.Line2D([0], [0], color=SECONDARY, lw=1.5,
                   linestyle=LINE_STYLES[pi % len(LINE_STYLES)],
                   label=pos.replace("_", " "))
        for pi, pos in enumerate(positions)
    ]
    ax.legend(handles=pos_handles, fontsize=6, frameon=True,
              framealpha=0.9, edgecolor=GRID_COLOR, loc="lower left",
              labelcolor=SECONDARY)

# Re-add metric legend to first panel (was overwritten)
ax = axes1[0]
handles = [
    plt.Line2D([0], [0], color=HE_COLOR,    lw=2,   label="Half Edge (left axis)"),
    plt.Line2D([0], [0], color=MORAN_COLOR, lw=2,   label="Moran's I (right axis)"),
    plt.Line2D([0], [0], color=DISSIM_COLOR, lw=1.5, alpha=0.7, label="Dissimilarity (left axis)"),
]
ax.legend(handles=handles, fontsize=6.5, frameon=True,
          framealpha=0.9, edgecolor=GRID_COLOR, loc="upper right",
          labelcolor=SECONDARY)

fig1.suptitle(
    "H4 T2 — Theoretical Diffusion: metric trajectories",
    fontsize=12, fontweight="bold", color=PRIMARY_INK, y=1.01,
)

out1 = OUT_DIR / "trajectories.png"
fig1.savefig(out1, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close(fig1)
print(f"Saved → {out1}")


# ── Figure 2: Divergence (Δ relative to step 0) ───────────────────────────────
# Normalise each series to [0, 1] across the entire run so both metrics are on
# the same scale, then show the signed change from step 0.

fig2, axes2 = plt.subplots(
    nrows, ncols,
    figsize=(13, 8),
    facecolor=BG,
    constrained_layout=True,
)
axes2 = axes2.flatten()

for ax_idx, gtype in enumerate(graph_types):
    ax = axes2[ax_idx]
    _setup_ax(ax)
    ax.axhline(0, color=MUTED, linewidth=0.8, linestyle="--", zorder=1)

    sub = df[df["graph_type"] == gtype]
    positions = sub["seed_position"].unique()

    for pi, pos in enumerate(positions):
        ls = LINE_STYLES[pi % len(LINE_STYLES)]
        lw = LINE_WEIGHTS[pi % len(LINE_WEIGHTS)]
        posdf = sub[sub["seed_position"] == pos].sort_values("step")

        he_0 = posdf["half_edge"].iloc[0]
        mo_0 = posdf["moran"].iloc[0]

        delta_he = posdf["half_edge"] - he_0
        delta_mo = posdf["moran"]     - mo_0

        ax.plot(posdf["step"], delta_he,
                color=HE_COLOR, linestyle=ls, linewidth=lw, zorder=3,
                label=f"{pos.replace('_',' ')} — HE")
        ax.plot(posdf["step"], delta_mo,
                color=MORAN_COLOR, linestyle=ls, linewidth=lw, alpha=0.85, zorder=3,
                label=f"{pos.replace('_',' ')} — Moran")

    ax.set_xlabel("Diffusion step", fontsize=8, color=SECONDARY)
    ax.set_ylabel("Change from step 0", fontsize=8, color=SECONDARY)
    ax.set_title(GRAPH_LABELS[gtype], fontsize=9, fontweight="bold",
                 color=PRIMARY_INK, pad=6)

    if ax_idx == 0:
        handles = [
            plt.Line2D([0], [0], color=HE_COLOR,    lw=2, label="Δ Half Edge"),
            plt.Line2D([0], [0], color=MORAN_COLOR, lw=2, label="Δ Moran's I"),
        ]
        ax.legend(handles=handles, fontsize=7, frameon=True,
                  framealpha=0.9, edgecolor=GRID_COLOR, loc="lower left",
                  labelcolor=SECONDARY)

    pos_handles = [
        plt.Line2D([0], [0], color=SECONDARY, lw=1.5,
                   linestyle=LINE_STYLES[pi % len(LINE_STYLES)],
                   label=pos.replace("_", " "))
        for pi, pos in enumerate(positions)
    ]
    ax.legend(handles=pos_handles, fontsize=6, frameon=True,
              framealpha=0.9, edgecolor=GRID_COLOR, loc="upper right",
              labelcolor=SECONDARY)

# Metric legend on first panel
ax = axes2[0]
handles = [
    plt.Line2D([0], [0], color=HE_COLOR,    lw=2, label="Δ Half Edge"),
    plt.Line2D([0], [0], color=MORAN_COLOR, lw=2, label="Δ Moran's I"),
]
ax.legend(handles=handles, fontsize=6.5, frameon=True,
          framealpha=0.9, edgecolor=GRID_COLOR, loc="lower left",
          labelcolor=SECONDARY)

fig2.suptitle(
    "H4 T2 — Divergence of Half Edge vs Moran's I  (change from step 0)",
    fontsize=12, fontweight="bold", color=PRIMARY_INK, y=1.01,
)

out2 = OUT_DIR / "divergence.png"
fig2.savefig(out2, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close(fig2)
print(f"Saved → {out2}")
