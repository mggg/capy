"""
H4 T2: Theoretical diffusion experiment runner.

For each graph in GRAPH_CATALOGUE, for each seed-cluster placement:
  1. Build the graph.
  2. Assign the graded initial state.
  3. Run the diffusion for N_STEPS steps.
  4. Record Half Edge, Moran's I, and Dissimilarity at each step.
  5. Save all results to data/diffusion_results.csv.

Run from the repo root:
    python experiments/h4_t2_theoretical_diffusion/scripts/run_experiment.py
"""

from pathlib import Path
import sys
import pandas as pd
import networkx as nx

EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXPERIMENT_DIR.parent.parent))  # repo root

from experiments.h4_t2_theoretical_diffusion.scripts.graphs import GRAPH_CATALOGUE, seed_clusters
from experiments.h4_t2_theoretical_diffusion.scripts.diffusion import (
    make_initial_state,
    diffusion_step,
    compute_metrics,
)

OUTPUT = EXPERIMENT_DIR / "data" / "diffusion_results.csv"

# ── Simulation parameters ─────────────────────────────────────────────────────
N_STEPS      = 60       # diffusion time steps
ALPHA        = 0.15     # diffusion rate per step
SEED_SHARE   = 0.85     # Black share at the seed cluster (distance 0)
DECAY_SCALE  = 2.0      # exponential decay length in graph hops
BASE_POP     = 100.0    # total population per node
CLUSTER_RADIUS = 2      # BFS ball radius for seed clusters

# ── Main loop ─────────────────────────────────────────────────────────────────

all_rows = []

for graph_type, constructor, kwargs in GRAPH_CATALOGUE:
    print(f"\n{'='*60}")
    print(f"Graph: {graph_type}")

    G = constructor(**kwargs)
    print(f"  nodes={G.number_of_nodes()}  edges={G.number_of_edges()}")

    seeds = seed_clusters(G, graph_type, cluster_radius=CLUSTER_RADIUS)

    for position, seed_nodes in seeds.items():
        print(f"  Seed position: {position}  ({len(seed_nodes)} seed nodes)")

        # Work on a fresh copy so graph attributes don't bleed between runs
        H = G.copy()

        state = make_initial_state(
            H, seed_nodes,
            seed_share=SEED_SHARE,
            decay_scale=DECAY_SCALE,
            base_pop=BASE_POP,
        )

        for step in range(N_STEPS + 1):
            metrics = compute_metrics(H, state)
            all_rows.append({
                "graph_type":  graph_type,
                "n_nodes":     H.number_of_nodes(),
                "n_edges":     H.number_of_edges(),
                "seed_position": position,
                "n_seed_nodes": len(seed_nodes),
                "step":        step,
                "alpha":       ALPHA,
                "seed_share":  SEED_SHARE,
                "decay_scale": DECAY_SCALE,
                **metrics,
            })

            if step < N_STEPS:
                state = diffusion_step(H, state, alpha=ALPHA)

        print(f"    done ({N_STEPS} steps).")

# ── Save ──────────────────────────────────────────────────────────────────────

df = pd.DataFrame(all_rows)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUTPUT, index=False)
print(f"\nSaved {len(df)} rows to {OUTPUT}")
print(df.groupby(["graph_type", "seed_position"])["step"].max().to_string())
