"""
Generates N_GRIDS grids at each clustering level, computes Moran's I and Capy
for every grid, and saves the results as JSON.

Output
------
  simulations/metrics_results.json — list of result dicts, one per grid

To plot the distribution histograms, run plot_clustering_figure.py afterwards:
  python experiment_code/assortativity_grids/scripts/simulate_grid_metrics.py
  python experiment_code/assortativity_grids/scripts/plot_clustering_figure.py
"""

import sys
import json
from networkx.readwrite import json_graph
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = (HERE / "../../../").resolve()
for p in (str(HERE), str(PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from experiment_code.assortativity_grids.utils.grid_utils import LEVELS, build_grid, compute_metrics

# Config 
N_GRIDS = 10000 # grids per clustering level
BASE_SEED = 1000 # seeds BASE_SEED ... BASE_SEED+N_GRIDS-1

# Output paths 
OUT_DIR = HERE.parent.parent.parent / "figures" / "assortativity_grids"
RESULTS_PATH = OUT_DIR / "grids" / "metrics_results.json"
EXEMPLARS_PATH = OUT_DIR / "grids" / "exemplar_grids.json"


# Simulation 

def run_simulation():
    """Build N_GRIDS grids per level; return a flat list of result dicts."""
    results = []
    seeds = range(BASE_SEED, BASE_SEED + N_GRIDS)
    for level in LEVELS:
        print(f"{level['label']} ({N_GRIDS} grids)...", flush=True)
        for seed in seeds:
            G = build_grid(level, seed)
            metrics = compute_metrics(G)
            results.append({
                "label": level["label"],
                "mode": level["mode"],
                "seed": seed,
                **metrics})
    return results


def save_results(results):
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved {len(results)} records → {RESULTS_PATH}")


def save_exemplars():
    """Build one grid per level (BASE_SEED) and save them as a JSON list.

    Each entry: {"label", "mode", "seed", "graph": <node-link dict>}.
    node_link_data preserves all node attributes (grid_pos, BLUE, ORANGE, …)
    and round-trips cleanly; node ids stay as integers.
    """
    exemplars = []
    for level in LEVELS:
        G = build_grid(level, BASE_SEED)
        exemplars.append({
            "label": level["label"],
            "mode":  level["mode"],
            "seed":  BASE_SEED,
            "graph": json_graph.node_link_data(G),
        })
    EXEMPLARS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EXEMPLARS_PATH, "w") as f:
        json.dump(exemplars, f, indent=2)
    print(f"Saved exemplar grids → {EXEMPLARS_PATH}")


if __name__ == "__main__":
    print(f"Running simulation: {N_GRIDS} grids × {len(LEVELS)} levels "
          f"= {N_GRIDS * len(LEVELS)} total")
    results = run_simulation()
    save_results(results)
    save_exemplars()
    print("Done. Run plot_clustering_figure.py to generate the figures.")
