"""
Creates two figures from data produced by simulate_grid_metrics.py:

  clustering_figure.{pdf,png} — 3 by 1 panel showing one exemplar map per
      clustering level (low / medium / high). Metric values (Moran's I and
      Capy) are shown below each panel. The exemplar grids are also saved as
      individual .json (gerrychain) and .png files.

  metric_distributions.png — overlapping histograms of both metrics across
      all simulated grids.

Both outputs require the files produced by simulate_grid_metrics.py:
  simulations/exemplar_grids.json
  simulations/metrics_results.json

To run:
  python experiment_code/assortativity_grids/scripts/simulate_grid_metrics.py
  python experiment_code/assortativity_grids/scripts/plot_clustering_figure.py
"""

import sys
import json
import numpy as np
from networkx.readwrite import json_graph
import gerrychain
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = (HERE / "../../../").resolve()
for p in (str(HERE), str(PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from experiment_code.assortativity_grids.utils.grid_utils import LEVELS, compute_metrics, share_array
from experiment_code.assortativity_grids.utils.viz_helpers import ORANGE, BLUE, GRID_METRICS, MORAN, CAPY


# Color maps
# Binary map for grid panels: 0 = ORANGE, 1 = BLUE
CMAP = mcolors.ListedColormap([ORANGE, BLUE])

# Colors for the metric-distribution histograms — one per metric.
# Blue / orange: clearly distinct and CVD-safe.
METRIC_COLORS = {"moran_P": MORAN, "half_edge_1": CAPY}

plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm",
                     "font.size": 14, "savefig.dpi": 300})


# Output paths

SIM_DIR = HERE.parent.parent.parent / "figures" / "assortativity_grids" / "grids"
EXEMPLARS_PATH = SIM_DIR / "exemplar_grids.json"
RESULTS_PATH = SIM_DIR / "metrics_results.json"

out_dir = HERE.parent.parent.parent / "figures" / "assortativity_grids"
GRID_DIR = HERE.parent.parent.parent / "figures" / "assortativity_grids"
JSON_DIR = GRID_DIR / "jsons"
PNG_DIR = GRID_DIR / "pngs"


# Load exemplar graphs 

def load_exemplars(path):
    """Read exemplar_grids.json, return list of (level_dict, gerrychain.Graph)."""
    with open(path) as f:
        entries = json.load(f)
    exemplars = []
    for entry in entries:
        nx_G = json_graph.node_link_graph(entry["graph"])
        # grid_pos was a tuple. JSON round-trips it as a list — convert back
        for node in nx_G.nodes():
            pos = nx_G.nodes[node].get("grid_pos")
            if isinstance(pos, list):
                nx_G.nodes[node]["grid_pos"] = tuple(pos)
        G = gerrychain.Graph(nx_G)
        level = next(lv for lv in LEVELS if lv["label"] == entry["label"])
        exemplars.append((level, G))
    return exemplars


if not EXEMPLARS_PATH.exists():
    raise FileNotFoundError(
        f"Exemplar grids not found at {EXEMPLARS_PATH}.\n"
        "Run simulate_grid_metrics.py first.")

exemplars = load_exemplars(EXEMPLARS_PATH)


def _grid_stem(level):
    return f"{level['mode']}_clustering_exemplar"


# def save_grid_json(G, level):
#     JSON_DIR.mkdir(parents=True, exist_ok=True)
#     path = JSON_DIR / f"{_grid_stem(level)}.json"
#     G.to_json(str(path))
#     return path


def save_grid_png(share, level):
    """Save a standalone PNG of the exemplar grid."""
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    path = PNG_DIR / f"{_grid_stem(level)}.png"
    fig, ax = plt.subplots(figsize=(3, 3))
    ax.pcolormesh(np.flipud(share), cmap=CMAP, vmin=0, vmax=1,
                  edgecolors="white", linewidth=0.5, antialiased=False)
    ax.set_aspect("equal")
    ax.tick_params(which="both", bottom=False, left=False,
                   labelbottom=False, labelleft=False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.savefig(str(path), bbox_inches="tight", facecolor="white", dpi=200)
    plt.close(fig)
    return path


# One PNG per exemplar grid

out_dir.mkdir(exist_ok=True)

for level, G in exemplars:
    share   = share_array(G)
    metrics = compute_metrics(G)

    fig, ax = plt.subplots(figsize=(2.5, 2.5))
    fig.patch.set_facecolor("white")

    # pcolormesh draws edges as part of the mesh geometry — they survive
    # rasterisation and PDF export reliably, unlike ax.grid() lines which
    # can land between pixels and vanish at certain figure sizes.
    # flipud so row 0 is at the top, matching the checkerboard layout.
    ax.pcolormesh(np.flipud(share), cmap=CMAP, vmin=0, vmax=1,
                  edgecolors="white", linewidth=0.3, antialiased=False)
    ax.set_aspect("equal")
    ax.tick_params(which="both", bottom=False, left=False,
                   labelbottom=False, labelleft=False)
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Encode metric values in filename instead of annotating the figure
    capy_val = metrics.get("half_edge_1", float("nan"))
    moran_val = metrics.get("moran_P", float("nan"))

    slug = level["label"].lower().replace(" ", "_")
    capy_str  = f"{capy_val:.2f}".replace(".", "p")
    moran_str = f"{moran_val:.2f}".replace(".", "p")
    path = out_dir / f"clustering_{slug}_capy{capy_str}_moran{moran_str}.png"
    fig.savefig(str(path), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Saved {path}")


# Metric distributions (v1 — overlapping histograms, both metrics on one axis)
# Commented out in favour of v2 below (two stacked subplots, one per metric).

# def plot_distributions(results):
#     """One PNG per clustering level; each shows Moran's I and Capy overlapping.
#     All files share the same x-axis limits and bin edges for easy comparison.
#     Horizontal lines at the top of each panel show the theoretical range of
#     each metric: Capy [0, 1] and Moran's I [−1, 1].
#     """
#     metric_keys = [k for k in GRID_METRICS if k in results[0]]
#
#     # Global x-range across all metrics and levels, with a small margin.
#     # Anchored to the theoretical bounds so the range lines are always visible.
#     all_vals = [r[k] for r in results for k in metric_keys if not np.isnan(r[k])]
#     x_min = min(min(all_vals), -1)
#     x_max = max(max(all_vals),  1)
#     x_pad = (x_max - x_min) * 0.05
#     x_lim = (x_min - x_pad, x_max + x_pad)
#
#     # Shared bin edges — same boundaries for every histogram so bar widths match
#     shared_bins = np.linspace(x_lim[0], x_lim[1], 91)  # 30 equal-width bins
#
#     # Theoretical ranges for the range-indicator lines
#     METRIC_RANGES = {"moran_P": (-1, 1), "half_edge_1": (0, 1)}
#     # y positions in axes fraction: Moran slightly above Capy
#     RANGE_Y = {"moran_P": 0.94, "half_edge_1": 0.92}
#
#     # Legend: histogram fills first, then range lines with explicit range labels.
#     # Line2D mimics the range-indicator lines drawn on the plot.
#     hist_handles = [
#         mpatches.Patch(color=METRIC_COLORS[k], alpha=0.55, label=GRID_METRICS[k])
#         for k in metric_keys
#     ]
#     range_handles = [
#         Line2D([0], [0], color=METRIC_COLORS[k], linewidth=2,
#                solid_capstyle="round",
#                label=f"{GRID_METRICS[k]} possible range "
#                      f"[{METRIC_RANGES[k][0]}, {METRIC_RANGES[k][1]}]")
#         for k in metric_keys
#     ]
#     legend_handles = hist_handles + range_handles
#
#     for level in LEVELS:
#         fig, ax = plt.subplots(figsize=(4.0, 3.8))
#         fig.patch.set_facecolor("white")
#
#         level_rows = [r for r in results if r["label"] == level["label"]]
#         means = {}
#         for key in metric_keys:
#             vals = [r[key] for r in level_rows if not np.isnan(r[key])]
#             means[key] = np.mean(vals)
#             ax.hist(vals, bins=shared_bins, alpha=0.55, color=METRIC_COLORS[key],
#                     edgecolor="none", label=GRID_METRICS[key])
#
#         # Fixed y-axis cap shared across all three histograms for comparability
#         ax.set_ylim(0, 4000)
#
#         # Mean lines — thin dashed vertical, with rotated numeric annotation.
#         # Fixed va="bottom" anchors all labels at the same y so they all rise
#         # from the same height regardless of where the mean falls on the x-axis.
#         for key in metric_keys:
#             mu = means[key]
#             color = METRIC_COLORS[key]
#             ax.axvline(mu, color=color, linewidth=0.8, linestyle="--", alpha=0.9)
#             ax.text(mu-0.07, 0.62, f"mean: {mu:.3f}",
#                     transform=ax.get_xaxis_transform(),
#                     color=color, fontsize=6, rotation=90,
#                     ha="center", va="bottom")
#
#         # Range-indicator lines: x in data coords, y in axes fraction.
#         trans = ax.get_xaxis_transform()
#         for key in metric_keys:
#             lo, hi = METRIC_RANGES[key]
#             y = RANGE_Y[key]
#             ax.plot([lo, hi], [y, y], transform=trans,
#                     color=METRIC_COLORS[key], linewidth=2,
#                     solid_capstyle="round", clip_on=False)
#
#         ax.set_xlim(x_lim)
#         ax.tick_params(labelsize=7, color="#aaaaaa")
#         ax.spines[["top", "right"]].set_visible(False)
#         ax.spines[["left", "bottom"]].set_color("#cccccc")
#
#         slug = level["label"].lower().replace(" ", "_")
#         path = out_dir / f"metric_distributions_{slug}.png"
#         fig.tight_layout()
#         fig.savefig(str(path), bbox_inches="tight", facecolor="white")
#         plt.close(fig)
#         print(f"Saved {path}")
#
#     # Standalone legend PNG
#     leg_fig, leg_ax = plt.subplots(figsize=(8, 0.5))
#     leg_ax.axis("off")
#     leg_ax.legend(handles=legend_handles, ncol=len(legend_handles),
#                   frameon=False, fontsize=7,
#                   loc="center", bbox_to_anchor=(0.5, 0.5))
#     leg_path = out_dir / "metric_distributions_legend.png"
#     leg_fig.savefig(str(leg_path), bbox_inches="tight", facecolor="white")
#     plt.close(leg_fig)
#     print(f"Saved {leg_path}")


# Metric distributions v2 — two stacked subplots, one per metric

# Fixed x-ranges per metric (theoretical bounds).
MORAN_XLIM = (-1, 1)
CAPY_XLIM = (0, 1)

# Bin edges for each metric. ~60 bins across the Moran range → bin width ≈ 0.033.
# Same bin width for Capy with 30 bins across [0, 1].
MORAN_BINS = np.linspace(-1, 1, 61)
CAPY_BINS = np.linspace(0, 1, 31)

METRIC_BINS = {"moran_P": MORAN_BINS, "half_edge_1": CAPY_BINS}
METRIC_XLIM = {"moran_P": MORAN_XLIM, "half_edge_1": CAPY_XLIM}


def plot_distributions_v2(results):
    """One PNG per clustering level: two subplots stacked vertically.
    Top subplot: Moran's I (x from −1 to 1).
    Bottom subplot: Capy (x from 0 to 1).
    No range-indicator lines. Mean line + rotated annotation preserved.
    Y-axis capped at 4000 for comparability across levels.
    """
    metric_keys = [k for k in GRID_METRICS if k in results[0]]

    # Legend handles — histogram fills only (no range lines)
    legend_handles = [
        mpatches.Patch(color=METRIC_COLORS[k], alpha=0.55, label=GRID_METRICS[k])
        for k in metric_keys
    ]

    for level in LEVELS:
        fig, axes = plt.subplots(2, 1, figsize=(4.0, 4.8))
        fig.patch.set_facecolor("white")

        level_rows = [r for r in results if r["label"] == level["label"]]
        means = {key: np.mean([r[key] for r in level_rows if not np.isnan(r[key])])
                 for key in metric_keys}

        for ax, key in zip(axes, metric_keys):
            vals = [r[key] for r in level_rows if not np.isnan(r[key])]
            mu = means[key]

            ax.hist(vals, bins=20,#METRIC_BINS[key],
                     alpha=0.65,
                    color=METRIC_COLORS[key], edgecolor="none")

            # Fixed y cap for cross-level comparability
            ax.set_yticks([])
            if key == "moran_P":
                ax.set_ylim(0, 1800)
                ax.set_xlim(-1, 1) # not the hard limit for the P matrix but the observed values do not go below -1 or above 1.
                ax.set_xticks([-1, -0.5, 0, 0.5, 1])
            else:
                ax.set_ylim(0, 1800)
                ax.set_xlim(*METRIC_XLIM[key])
                # ax.set_xticks([0, 0.5, 1])
            # ax.set_xlim(*METRIC_XLIM[key])

            # Thin dashed mean line — no text annotation
            ax.axvline(mu, color="#3a3937",
                       linewidth=0.8, linestyle="--", alpha=0.9)

            # ax.set_ylabel(GRID_METRICS[key], fontsize=7, color="#3a3937")
            # ax.tick_params(labelsize=11, color=None)
            ax.spines[["top", "right"]].set_visible(False)
            ax.spines[["left", "bottom"]].set_color("#cccccc")

        slug = level["label"].lower().replace(" ", "_")
        avg_capy = means.get("half_edge_1", float("nan"))
        avg_moran = means.get("moran_P", float("nan"))
        path = out_dir / f"metric_distributions_{slug}_ave_capy{avg_capy:.2f}_moran{avg_moran:.2f}"
        path = str(path).replace('.', 'p')  # avoid dots in filename
        path = f"{path}.png"
        fig.tight_layout()
        fig.savefig(str(path), bbox_inches="tight", facecolor="white")
        plt.close(fig)
        print(f"Saved {path}")

    # Standalone legend PNG — histogram fills only, one horizontal row.
    # Use figlegend so matplotlib sizes the figure tightly around the legend text.
    leg_fig = plt.figure()
    leg = leg_fig.legend(handles=legend_handles, ncol=len(legend_handles),
                         frameon=False, fontsize=7,
                         loc="center", bbox_to_anchor=(0.5, 0.5))
    leg_fig.canvas.draw()
    bbox = leg.get_window_extent().transformed(leg_fig.dpi_scale_trans.inverted())
    leg_fig.set_size_inches(bbox.width + 0.05, bbox.height + 0.05)
    leg_path = out_dir / "metric_distributions_legend.png"
    leg_fig.savefig(str(leg_path), bbox_inches="tight", pad_inches=0.02,
                    facecolor="white")
    plt.close(leg_fig)
    print(f"Saved {leg_path}")


if RESULTS_PATH.exists():
    with open(RESULTS_PATH) as f:
        results = json.load(f)
    plot_distributions_v2(results)
else:
    print(f"No simulation data found at {RESULTS_PATH}. Run simulate_grid_metrics.py first to generate the distribution plot.")
