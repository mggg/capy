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

plt.rcParams.update({"font.family": "sans-serif", "font.size": 7, "savefig.dpi": 300})


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

    # ax.set_ylabel(level["label"], fontsize=8,
    #               rotation=90, labelpad=8, color="#3a3937")

    metric_lines = [f"{GRID_METRICS[k]} = {metrics[k]:.3f}"
                    for k in GRID_METRICS if k in metrics]
    ax.set_xlabel("\n".join(metric_lines), fontsize=5.5, linespacing=1.75,
                  labelpad=5, color="#3a3937")

    slug = level["label"].lower().replace(" ", "_")
    path = out_dir / f"clustering_{slug}.png"
    fig.savefig(str(path), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Saved {path}")


# Metric distributions 

def plot_distributions(results):
    """One PNG per clustering level; each shows Moran's I and Capy overlapping.
    All files share the same x-axis limits and bin edges for easy comparison.
    Horizontal lines at the top of each panel show the theoretical range of
    each metric: Capy [0, 1] and Moran's I [−1, 1].
    """
    metric_keys = [k for k in GRID_METRICS if k in results[0]]

    # Global x-range across all metrics and levels, with a small margin.
    # Anchored to the theoretical bounds so the range lines are always visible.
    all_vals = [r[k] for r in results for k in metric_keys if not np.isnan(r[k])]
    x_min = min(min(all_vals), -1)
    x_max = max(max(all_vals),  1)
    x_pad = (x_max - x_min) * 0.05
    x_lim = (x_min - x_pad, x_max + x_pad)

    # Shared bin edges — same boundaries for every histogram so bar widths match
    shared_bins = np.linspace(x_lim[0], x_lim[1], 91)  # 30 equal-width bins

    # Theoretical ranges for the range-indicator lines
    METRIC_RANGES = {"moran_P": (-1, 1), "half_edge_1": (0, 1)}
    # y positions in axes fraction: Moran slightly above Capy
    RANGE_Y = {"moran_P": 0.94, "half_edge_1": 0.92}
    # RANGE_Y = {"moran_P": -0.02, "half_edge_1": -0.035}

    # Legend: histogram fills first, then range lines with explicit range labels.
    # Line2D mimics the range-indicator lines drawn on the plot.
    hist_handles = [
        mpatches.Patch(color=METRIC_COLORS[k], alpha=0.55, label=GRID_METRICS[k])
        for k in metric_keys
    ]
    range_handles = [
        Line2D([0], [0], color=METRIC_COLORS[k], linewidth=2,
               solid_capstyle="round",
               label=f"{GRID_METRICS[k]} possible range "
                     f"[{METRIC_RANGES[k][0]}, {METRIC_RANGES[k][1]}]")
        for k in metric_keys
    ]
    legend_handles = hist_handles + range_handles

    for level in LEVELS:
        fig, ax = plt.subplots(figsize=(4.0, 3.8))
        fig.patch.set_facecolor("white")

        level_rows = [r for r in results if r["label"] == level["label"]]
        means = {}
        for key in metric_keys:
            vals = [r[key] for r in level_rows if not np.isnan(r[key])]
            means[key] = np.mean(vals)
            ax.hist(vals, bins=shared_bins, alpha=0.55, color=METRIC_COLORS[key],
                    edgecolor="none", label=GRID_METRICS[key])

        # Fixed y-axis cap shared across all three histograms for comparability
        ax.set_ylim(0, 4000)

        # Mean lines — thin dashed vertical, with rotated numeric annotation.
        # Fixed va="bottom" anchors all labels at the same y so they all rise
        # from the same height regardless of where the mean falls on the x-axis.
        for key in metric_keys:
            mu = means[key]
            color = METRIC_COLORS[key]
            ax.axvline(mu, color=color, linewidth=0.8, linestyle="--", alpha=0.9)
            ax.text(mu-0.07, 0.62, f"mean: {mu:.3f}",
                    transform=ax.get_xaxis_transform(),
                    color=color, fontsize=6, rotation=90,
                    ha="center", va="bottom")

        # Range-indicator lines: x in data coords, y in axes fraction.
        # ax.get_xaxis_transform() gives exactly that blended coordinate system.
        trans = ax.get_xaxis_transform()
        for key in metric_keys:
            lo, hi = METRIC_RANGES[key]
            y = RANGE_Y[key]
            ax.plot([lo, hi], [y, y], transform=trans,
                    color=METRIC_COLORS[key], linewidth=2,
                    solid_capstyle="round", clip_on=False)

        # ax.set_xlabel("Metric value", fontsize=8, color="#3a3937")
        ax.set_xlim(x_lim)
        ax.tick_params(labelsize=7, color="#aaaaaa")
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color("#cccccc")
        # ax.legend(handles=legend_handles, frameon=False, fontsize=6,
        #           loc="upper left", bbox_to_anchor=(0, 0.9))

        slug = level["label"].lower().replace(" ", "_")
        path = out_dir / f"metric_distributions_{slug}.png"
        fig.tight_layout()
        fig.savefig(str(path), bbox_inches="tight", facecolor="white")
        plt.close(fig)
        print(f"Saved {path}")

    # Standalone legend PNG — all items in one horizontal row.
    # bbox_inches="tight" crops to the legend content, so figure size only
    # needs to be large enough for the legend not to be clipped before saving.
    leg_fig, leg_ax = plt.subplots(figsize=(8, 0.5))
    leg_ax.axis("off")
    leg_ax.legend(handles=legend_handles, ncol=len(legend_handles),
                  frameon=False, fontsize=7,
                  loc="center", bbox_to_anchor=(0.5, 0.5))
    leg_path = out_dir / "metric_distributions_legend.png"
    leg_fig.savefig(str(leg_path), bbox_inches="tight", facecolor="white")
    plt.close(leg_fig)
    print(f"Saved {leg_path}")


if RESULTS_PATH.exists():
    with open(RESULTS_PATH) as f:
        results = json.load(f)
    plot_distributions(results)
else:
    print(f"No simulation data found at {RESULTS_PATH}. "
          f"Run simulate_grid_metrics.py first to generate the distribution plot.")
