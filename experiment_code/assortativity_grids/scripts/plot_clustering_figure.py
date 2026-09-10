#!/usr/bin/env python3
"""
This code create a 3 by 3 figure showing modified checkerboard grids at three clustering levels:
  Row 1 — low clustering (PERTURB_PROB = 0.25)
  Row 2 — medium clustering (PERTURB_PROB = 0.40)
  Row 3 — high clustering (PERTURB_PROB = 0.60)

Each column is an independent random seed so that we can see the variability of the metrics at each clustering level.
Metric values (Capy and Moran's I) are shown below each grid.

To run: python experiments/h4_t2_theoretical_diffusion/scripts/plot_clustering_figure.py
"""

import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import networkx as nx
import gerrychain
from pathlib import Path

# ── Project root ───────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = (HERE / "../../../").resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pipeline.metrics as m
from experiments.h4_t2_theoretical_diffusion.utils.viz_helpers import (ORANGE, BLUE, GRID_METRICS)

# GRID_METRICS = {"moran_P": "Moran's I", "dissimilarity_1": "Dissimilarity",
#                 "half_edge_1": "Capy"}


ROWS, COLS = 10, 10
CELL_POP = 100
MODE = "checkerboard_perturbed"
SEEDS = [42, 7, 123] # one column per seed

LEVELS = [0.05, 0.40, 0.85] # PERTURB_PROB: low / medium / high
LEVEL_LABELS = ["Low clustering", "Medium clustering", "High clustering"]


def build_grid(rows, cols, cell_pop=100, seed=42, perturb_prob=0.15):
    """
    Create a 4-connected grid with checkerboard_perturbed colouring. First it initializes a pure checkerboard, then it does a raster walk through the grid, and each cell adopts its predecessor's colour with probability perturb_prob.
    """
    nx_G = nx.grid_2d_graph(rows, cols)
    nx_G = nx.convert_node_labels_to_integers(nx_G, label_attribute="grid_pos")
    nodes = list(nx_G.nodes())
    n = len(nodes)
    pos = {nd: nx_G.nodes[nd]["grid_pos"] for nd in nodes}

    # Create a pure checkerboard
    board = np.zeros((rows, cols), dtype=int)
    for r in range(rows):
        for c in range(cols):
            board[r, c] = cell_pop if (r + c) % 2 == 0 else 0

    # Do a raster walk: each cell adopts predecessor's color w/ prob p
    rng  = np.random.default_rng(seed)
    prev = board[0, 0]
    for r in range(rows):
        for c in range(cols):
            if r == 0 and c == 0:
                prev = board[r, c]
                continue
            if rng.random() < perturb_prob:
                board[r, c] = prev
            prev = board[r, c]

    blue_arr = np.array([board[pos[nd][0], pos[nd][1]] for nd in nodes])

    for i, node in enumerate(nodes):
        b = int(blue_arr[i])
        r = cell_pop - b # exhaustive groups
        nx_G.nodes[node].update(BLUE=b, ORANGE=r, TOTAL=cell_pop, TOTPOP=cell_pop, WHITE=b, BLACK=r, POC=r)

    return gerrychain.Graph(nx_G)


def share_array(G, rows, cols):
    """Return a (rows, cols) float array of BLUE share per cell."""
    arr = np.zeros((rows, cols))
    for node in G.nodes():
        r, c = G.nodes[node]["grid_pos"]
        tot = G.nodes[node]["TOTPOP"]
        arr[r, c] = G.nodes[node]["BLUE"] / tot if tot > 0 else 0.5
    return arr


def compute_metrics(G):
    """Compute the three display metrics."""
    spes = m.skew_prime_exact(G, "BLUE", "ORANGE", lam=1)
    speo = m.skew_prime_exact(G, "ORANGE",  "BLUE", lam=1)

    try:
        moran = m.moran(G, "BLUE", "TOTAL")["moran_P"]
    except ZeroDivisionError:
        moran = float("nan")

    return {"moran_P": moran,
        # "dissimilarity_1": m.dissimilarity(G, "BLUE", "ORANGE", 1),
        "half_edge_1": 0.5 * (spes + speo)}


# Plot
# Binary colormap: 0 is ORANGE, 1 is BLUE
CMAP = mcolors.ListedColormap([ORANGE, BLUE])

plt.rcParams.update({"font.family": "sans-serif",
    "font.size": 7, "savefig.dpi": 300})

NCOLS = len(SEEDS)
NROWS = len(LEVELS)

fig, axes = plt.subplots(NROWS, NCOLS,
    figsize=(6.0, 7.2), gridspec_kw={"hspace": 0.50, "wspace": 0.06})
fig.patch.set_facecolor("white")

for row_idx, (perturb_prob, row_label) in enumerate(zip(LEVELS, LEVEL_LABELS)):
    for col_idx, seed in enumerate(SEEDS):
        ax = axes[row_idx, col_idx]

        G = build_grid(ROWS, COLS, CELL_POP, seed=seed,
                             perturb_prob=perturb_prob)
        share = share_array(G, ROWS, COLS)
        metrics = compute_metrics(G)

        # Grid image
        # pcolormesh is a fix, it draws edges as part of the mesh geometry — they survive rasterisation and PDF export reliably, unlike ax.grid() lines which
        # can land between pixels and vanish at certain figure sizes.
        # flipud so row 0 is at the top, matching the checkerboard layout.
        ax.pcolormesh(np.flipud(share), cmap=CMAP, vmin=0, vmax=1,
                      edgecolors="white", linewidth=0.3, antialiased=False)
        ax.set_aspect("equal")
        ax.tick_params(which="both", bottom=False, left=False,
                       labelbottom=False, labelleft=False)
        for spine in ax.spines.values():
            spine.set_visible(False)

        # Row label (left column only)
        if col_idx == 0:
            ax.set_ylabel(row_label, fontsize=8,
                # fontweight="semibold",
                rotation=90, labelpad=8, color="#3a3937")

        # Metric text below pictures
        lines = [f"{GRID_METRICS[k]} = {metrics[k]:.3f}"
            for k in GRID_METRICS # dict order: Moran, Capy
            if k in metrics]
        ax.set_xlabel("\n".join(lines),fontsize=6.5, linespacing=1.75, labelpad=5,
            color="#3a3937")

out_dir = HERE.parent / "figures"
out_dir.mkdir(exist_ok=True)
out_stem = out_dir / "clustering_figure"
fig.savefig(f"{out_stem}.pdf", bbox_inches="tight", facecolor="white")
fig.savefig(f"{out_stem}.png", bbox_inches="tight", facecolor="white")
print(f"Saved {out_stem}.pdf and .png")
# plt.show()
