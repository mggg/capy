"""
Shared grid builders, metric helpers, and constants for assortativity-grid
experiments. Imported by plot_clustering_figure.py and simulate_grid_metrics.py.
"""

import sys
import numpy as np
import networkx as nx
import gerrychain
from pathlib import Path
from scipy.ndimage import gaussian_filter

# Project root
HERE = Path(__file__).resolve().parent          # scripts/
PROJECT_ROOT = (HERE / "../../../").resolve()   # capy-bara/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import capy_core.metrics as m

# Shared constants 
ROWS, COLS = 10, 10
CELL_POP = 100

LEVELS = [
    {"label": "Low clustering",    "mode": "annealing"},
    {"label": "Medium clustering", "mode": "random"},
    {"label": "High clustering",   "mode": "gaussian", "sigma": 1.6}]


# Node attribute helper 

def _attach_attrs(nx_G, blue_arr, cell_pop):
    """Write BLUE/ORANGE/TOTAL/TOTPOP onto every node."""
    for i, node in enumerate(nx_G.nodes()):
        b = int(blue_arr[i])
        r = cell_pop - b
        nx_G.nodes[node].update(
            BLUE=b, ORANGE=r, TOTAL=cell_pop, TOTPOP=cell_pop)


# Grid builders

def build_grid_low(rows, cols, cell_pop=100, seed=42, n_steps=20_000, accept_prob=0.01):
    """
    Simulated annealing that maximises cut edges (cross-group adjacencies).

    Starts from a random half-blue / half-orange assignment and iteratively
    proposes swaps between a blue node and an orange node. A swap is always
    accepted if it increases the cut-edge count; otherwise it is accepted
    with probability `accept_prob` so the search can escape local minima.

    For a grid graph the global optimum is the checkerboard (every edge is a
    cut edge), so the SA converges toward near-checkerboard configurations —
    strongly negative Moran's I = low clustering. Unlike the simple
    checkerboard-with-perturbation approach, different seeds reach different
    convergence points, producing a natural (rather than one-sided) distribution.

    Adapted from make_low_assortativity_grids.py.
    """
    nx_G = nx.grid_2d_graph(rows, cols)
    nx_G = nx.convert_node_labels_to_integers(nx_G, label_attribute="grid_pos")
    nodes = list(nx_G.nodes())
    n = len(nodes)

    rng = np.random.default_rng(seed)

    # Initial assignment: exactly half blue (1), half orange (0), shuffled
    assignment = np.zeros(n, dtype=np.int8)
    assignment[: n // 2] = 1
    rng.shuffle(assignment)

    # colour dict for O(1) node-colour lookup during SA
    color = dict(zip(nodes, assignment.tolist()))  # 1 = blue, 0 = orange

    def _swap_delta(i, j):
        """Change in cut-edge count from swapping the colours of nodes i and j."""
        if color[i] == color[j]:
            return 0
        delta = 0
        for u in (i, j):
            for nbr in nx_G.neighbors(u):
                if nbr == i or nbr == j:   # skip the i–j edge itself
                    continue
                # cut status before and after the swap
                delta += int((1 - color[u]) != color[nbr]) - int(color[u] != color[nbr])
        return delta

    blue_nodes   = [nd for nd in nodes if color[nd] == 1]
    orange_nodes = [nd for nd in nodes if color[nd] == 0]

    for _ in range(n_steps):
        i = blue_nodes  [int(rng.integers(len(blue_nodes)))]
        j = orange_nodes[int(rng.integers(len(orange_nodes)))]

        d = _swap_delta(i, j)
        if d > 0 or rng.random() < accept_prob:
            color[i], color[j] = color[j], color[i]
            blue_nodes.remove(i);   blue_nodes.append(j)
            orange_nodes.remove(j); orange_nodes.append(i)

    blue_arr = np.array([cell_pop * color[nd] for nd in nodes])
    _attach_attrs(nx_G, blue_arr, cell_pop)
    return gerrychain.Graph(nx_G)


def build_grid_low_simple(rows, cols, cell_pop=100, seed=42, perturb_prob=0.05):
    """
    Checkerboard with raster-walk perturbation (original simpler approach).
    Starts as a pure checkerboard. Each cell then adopts its predecessor's
    color with probability perturb_prob. Small p = near-perfect checkerboard
    = strongly negative Moran's I = low clustering.

    Produces a one-sided distribution (hard lower bound at the checkerboard
    minimum); preserved for reference. Use build_grid_low for simulation.
    """
    nx_G = nx.grid_2d_graph(rows, cols)
    nx_G = nx.convert_node_labels_to_integers(nx_G, label_attribute="grid_pos")
    nodes = list(nx_G.nodes())
    pos = {nd: nx_G.nodes[nd]["grid_pos"] for nd in nodes}

    board = np.zeros((rows, cols), dtype=int)
    for r in range(rows):
        for c in range(cols):
            board[r, c] = cell_pop if (r + c) % 2 == 0 else 0

    rng = np.random.default_rng(seed)
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
    _attach_attrs(nx_G, blue_arr, cell_pop)
    return gerrychain.Graph(nx_G)


def build_grid_medium(rows, cols, cell_pop=100, seed=42):
    """
    Uniform random assignment: exactly half the cells get BLUE=cell_pop, the
    other half BLUE=0, in a shuffled order. No spatial correlation = Moran's I
    near 0 = medium clustering.
    """
    nx_G = nx.grid_2d_graph(rows, cols)
    nx_G = nx.convert_node_labels_to_integers(nx_G, label_attribute="grid_pos")
    nodes = list(nx_G.nodes())
    n = len(nodes)

    rng = np.random.default_rng(seed)
    assignment = np.zeros(n, dtype=int)
    assignment[: n // 2] = cell_pop
    rng.shuffle(assignment)

    _attach_attrs(nx_G, assignment, cell_pop)
    return gerrychain.Graph(nx_G)


def build_grid_high(rows, cols, cell_pop=100, seed=42, sigma=1.6):
    """
    Gaussian-smoothed noise, thresholded at the median.
    The smooth field produces spatially contiguous blobs = strongly positive
    Moran's I = high clustering.
    """
    nx_G = nx.grid_2d_graph(rows, cols)
    nx_G = nx.convert_node_labels_to_integers(nx_G, label_attribute="grid_pos")
    nodes = list(nx_G.nodes())
    n = len(nodes)
    pos = {nd: nx_G.nodes[nd]["grid_pos"] for nd in nodes}

    rng = np.random.default_rng(seed)
    noise = rng.random((rows, cols))
    smooth = gaussian_filter(noise, sigma=sigma)

    # Threshold so exactly half of cells are BLUE
    n_blue = n // 2
    flat = smooth.flatten()
    cut = np.partition(flat, -n_blue)[-n_blue]
    grid_assign = (smooth >= cut).astype(int) # 1 = BLUE, 0 = ORANGE

    blue_arr = np.array([grid_assign[pos[nd][0], pos[nd][1]] * cell_pop
                         for nd in nodes])
    _attach_attrs(nx_G, blue_arr, cell_pop)
    return gerrychain.Graph(nx_G)


def build_grid(level, seed, rows=ROWS, cols=COLS, cell_pop=CELL_POP):
    """Dispatch to the correct builder based on a level config dict."""
    mode = level["mode"]
    if mode == "annealing":
        return build_grid_low(rows, cols, cell_pop, seed=seed)
    if mode == "random":
        return build_grid_medium(rows, cols, cell_pop, seed=seed)
    if mode == "gaussian":
        return build_grid_high(rows, cols, cell_pop, seed=seed,
                               sigma=level["sigma"])
    raise ValueError(f"Unknown mode: {mode!r}")


def compute_metrics(G):
    """Return dict with moran_P and half_edge_1 (Capy)."""
    spes = m.skew_prime_exact(G, "BLUE", "ORANGE", lam=1)
    speo = m.skew_prime_exact(G, "ORANGE", "BLUE", lam=1)
    try:
        moran = m.moran(G, "BLUE", "TOTAL")["moran_P"]
    except ZeroDivisionError:
        moran = float("nan")
    return {"moran_P": moran, "half_edge_1": 0.5 * (spes + speo)}


# Visualisation helper

def share_array(G, rows=ROWS, cols=COLS):
    """Return a (rows, cols) float array of BLUE share per cell."""
    arr = np.zeros((rows, cols))
    for node in G.nodes():
        r, c = G.nodes[node]["grid_pos"]
        tot = G.nodes[node]["TOTPOP"]
        arr[r, c] = G.nodes[node]["BLUE"] / tot if tot > 0 else 0.5
    return arr
