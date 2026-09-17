"""
Creates two figures from data produced by simulate_grid_metrics.py:

  clustering_figure.png is a 3 by 1 panel showing one exemplar map per
      clustering level (low, medium, high). The exemplar grids are also saved as
      individual .json (gerrychain) and .png files.

  metric_distributions.png shows overlapping histograms of both metrics across
      all simulated grids.

Both outputs require the files produced by simulate_grid_metrics.py:
  simulations/exemplar_grids.json
  simulations/metrics_results.json

To run:
  python experiment_code/assortativity_grids/scripts/simulate_grid_metrics.py
  python experiment_code/assortativity_grids/scripts/plot_grids_and_metric_histogram.py
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
from experiment_code.visualization_settings import ORANGE, BLUE, GRID_METRICS, MORAN, CAPY, SECONDARY


# Color maps
# Binary map for grid panels: 0 = ORANGE, 1 = BLUE
CMAP = mcolors.ListedColormap([ORANGE, BLUE])

# Colors for the metric-distribution histograms, one per metric.
# Blue / orange: clearly distinct and CVD-safe.
METRIC_COLORS = {"moran_P": MORAN, "half_edge_1": CAPY}

# Fixed x-ranges per metric (theoretical bounds).
MORAN_XLIM = (-1, 1)
CAPY_XLIM = (0, 1)

# Bin edges for each metric. ~60 bins across the Moran range, bin width ≈ 0.033.
# Same bin width for Capy with 30 bins across [0, 1].
MORAN_BINS = np.linspace(-1, 1, 61)
CAPY_BINS = np.linspace(0, 1, 31)

METRIC_BINS = {"moran_P": MORAN_BINS, "half_edge_1": CAPY_BINS}
METRIC_XLIM = {"moran_P": MORAN_XLIM, "half_edge_1": CAPY_XLIM}





# Output paths

SIM_DIR = HERE / "simulations"
EXEMPLARS_PATH = SIM_DIR / "exemplar_grids.json"
RESULTS_PATH = SIM_DIR / "metrics_results.json"

out_dir = PROJECT_ROOT / "figures" / "assortativity_grids"
GRID_DIR = PROJECT_ROOT / "figures" / "assortativity_grids"
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




def _grid_stem(level):
    return f"{level['mode']}_clustering_exemplar"


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


def plot_metric_histogram(ax, vals, key, mean):
    """Draw one metric histogram with its mean line."""
    ax.hist(vals, bins=20,
             alpha=1.0,
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

    # Thin dashed mean line
    ax.axvline(mean, color=SECONDARY,
               linewidth=0.8, linestyle="--", alpha=0.9)

    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#cccccc")


def plot_distributions(results):
    """One PNG per clustering level: two subplots to be stacked vertically.
    Top subplot shows Moran's I
    Bottom subplot shows Capy.
    Y-axis capped at 4000 for comparability.
    """
    metric_keys = [k for k in GRID_METRICS if k in results[0]]

    for level in LEVELS:
        fig, axes = plt.subplots(2, 1, figsize=(4.0, 4.8))

        level_rows = [r for r in results if r["label"] == level["label"]]
        means = {key: np.mean([r[key] for r in level_rows if not np.isnan(r[key])])
                 for key in metric_keys}

        for ax, key in zip(axes, metric_keys):
            vals = [r[key] for r in level_rows if not np.isnan(r[key])]
            mu = means[key]

            plot_metric_histogram(ax, vals, key, mu)

        slug = level["label"].lower().replace(" ", "_")
        avg_capy = means.get("half_edge_1", float("nan"))
        avg_moran = means.get("moran_P", float("nan"))
        filename = f"metric_distributions_{slug}_ave_capy{avg_capy:.2f}_moran{avg_moran:.2f}"
        filename = filename.replace('.', 'p') # avoid dots in filename
        path = out_dir / f"{filename}.png"
        fig.tight_layout()
        fig.savefig(str(path), bbox_inches="tight")
        plt.close(fig)
        print(f"Saved {path}")


def save_distribution_legend(metric_keys):
    """Save a standalone horizontal legend for the selected metric histograms."""
    legend_handles = [
        mpatches.Patch(facecolor=METRIC_COLORS[k], edgecolor="none", alpha=1.0, label=GRID_METRICS[k])
        for k in metric_keys]

    # Standalone legend PNG, one horizontal row.
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


def main():
    """Load simulation data and save the exemplar and distribution figures."""
    plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm",
                         "font.size": 14, "savefig.dpi": 300})

    if not EXEMPLARS_PATH.exists():
        raise FileNotFoundError(
            f"Exemplar grids not found at {EXEMPLARS_PATH}.\n"
            "Run simulate_grid_metrics.py first.")

    exemplars = load_exemplars(EXEMPLARS_PATH)

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

    if RESULTS_PATH.exists():
        with open(RESULTS_PATH) as f:
            results = json.load(f)
        plot_distributions(results)
        metric_keys = [k for k in GRID_METRICS if k in results[0]]
        save_distribution_legend(metric_keys)
    else:
        print(f"No simulation data found at {RESULTS_PATH}. Run simulate_grid_metrics.py first to generate the distribution plot.")


if __name__ == "__main__":
    main()
