"""
Diffusion model, initial state assignment, and metric computation for H4 T2.

Population model
----------------
Each node carries BLACK and WHITE counts (floats during simulation).
WHITE is fixed throughout; only BLACK diffuses.
Total population at a node = BLACK + WHITE.

Diffusion rule
--------------
Standard symmetric graph diffusion on BLACK only:

    B_i(t+1) = B_i(t) + alpha * sum_j [ (B_j(t) - B_i(t)) / deg(i) ]

where the sum is over neighbours j.  This conserves sum(BLACK) exactly.

Initial state
-------------
Seed cluster nodes receive seed_share * base_pop BLACK and the rest WHITE.
Nodes at graph-distance d from the nearest seed node receive:
    black_share(d) = seed_share * exp(-d / decay_scale)
so there is a smooth gradient outward from the cluster.
"""

import numpy as np
import networkx as nx
import scipy.sparse


# ── Initial state ─────────────────────────────────────────────────────────────

def make_initial_state(G, seed_nodes, seed_share=0.85, decay_scale=2.0, base_pop=100.0):
    """
    Return {node: {"BLACK": float, "WHITE": float}} for every node in G.

    Parameters
    ----------
    G : networkx.Graph
    seed_nodes : list of node IDs forming the initial cluster
    seed_share : Black share assigned to seed nodes (distance 0)
    decay_scale : exponential decay length (in graph hops)
    base_pop : total population at every node
    """
    dist_to_seed = {}
    for seed in seed_nodes:
        for node, d in nx.single_source_shortest_path_length(G, seed).items():
            if node not in dist_to_seed or d < dist_to_seed[node]:
                dist_to_seed[node] = d

    state = {}
    for node in G.nodes():
        d = dist_to_seed.get(node, float("inf"))
        black_share = seed_share * np.exp(-d / decay_scale) if d < np.inf else 0.0
        black_share = max(0.0, min(1.0, black_share))
        state[node] = {
            "BLACK": black_share * base_pop,
            "WHITE": (1.0 - black_share) * base_pop,
        }
    return state


# ── Diffusion step ─────────────────────────────────────────────────────────────

def diffusion_step(G, state, alpha=0.15):
    """
    Apply one step of symmetric graph diffusion to BLACK population.
    Returns a new state dict; original is not modified.
    """
    new_black = {}
    for node in G.nodes():
        neighbors = list(G.neighbors(node))
        if not neighbors:
            new_black[node] = state[node]["BLACK"]
            continue
        deg = len(neighbors)
        delta = alpha * sum(
            state[nb]["BLACK"] - state[node]["BLACK"]
            for nb in neighbors
        ) / deg
        new_black[node] = state[node]["BLACK"] + delta

    return {
        node: {"BLACK": new_black[node], "WHITE": state[node]["WHITE"]}
        for node in G.nodes()
    }


# ── Metric computation ────────────────────────────────────────────────────────
# Re-implemented without functools.cache so we can call per-step on the same
# graph topology with changing node attributes.

def _apply_state(G, state):
    """Stamp BLACK/WHITE/TOTPOP onto G in-place and return G."""
    for node, vals in state.items():
        G.nodes[node]["BLACK"] = vals["BLACK"]
        G.nodes[node]["WHITE"] = vals["WHITE"]
        G.nodes[node]["TOTPOP"] = vals["BLACK"] + vals["WHITE"]
    return G


def _angle1(G, a, b, lam=1.0):
    """<a, b>_lam = lam * sum_i a_i*b_i + sum_{(i,j) in E} (a_i*b_j + a_j*b_i)"""
    self_sum = sum(G.nodes[n][a] * G.nodes[n][b] for n in G.nodes())
    edge_sum = sum(
        G.nodes[u][a] * G.nodes[v][b] + G.nodes[v][a] * G.nodes[u][b]
        for u, v in G.edges()
    )
    return lam * self_sum + edge_sum


def half_edge(G, state, lam=1.0):
    """
    Half Edge at lambda=lam.
    HE = 0.5 * (skew'_self + skew'_other)
    skew'_self  = <X,X> / (<X,X> + <X,Y>)
    skew'_other = <Y,Y> / (<Y,Y> + <X,Y>)
    """
    _apply_state(G, state)
    xx = _angle1(G, "BLACK", "BLACK", lam)
    yy = _angle1(G, "WHITE", "WHITE", lam)
    xy = _angle1(G, "BLACK", "WHITE", lam)
    if (xx + xy) == 0 or (yy + xy) == 0:
        return np.nan
    return 0.5 * (xx / (xx + xy) + yy / (yy + xy))


def moran_adjacency(G, state):
    """
    Moran's I with raw adjacency weight matrix (moran_A from pipeline).
    Computed on Black share = BLACK / TOTPOP.
    """
    _apply_state(G, state)
    nodes = list(G.nodes())
    n = len(nodes)
    idx = {node: i for i, node in enumerate(nodes)}

    shares = np.array([
        G.nodes[node]["BLACK"] / G.nodes[node]["TOTPOP"]
        for node in nodes
    ])
    shares_c = shares - shares.mean()

    denom = float(shares_c @ shares_c)
    if denom == 0:
        return np.nan

    # Build adjacency matrix
    rows, cols = [], []
    for u, v in G.edges():
        rows += [idx[u], idx[v]]
        cols += [idx[v], idx[u]]
    vals = np.ones(len(rows))
    A = scipy.sparse.csr_matrix((vals, (rows, cols)), shape=(n, n))

    S0 = float(A.sum())
    numerator = float(shares_c @ A @ shares_c)
    return (n / S0) * numerator / denom


def dissimilarity(G, state):
    """Classic dissimilarity index (p=1 from pipeline)."""
    _apply_state(G, state)
    total_black = sum(G.nodes[n]["BLACK"] for n in G.nodes())
    total_white = sum(G.nodes[n]["WHITE"] for n in G.nodes())
    if total_black == 0 or total_white == 0:
        return np.nan
    s = 0.0
    for node in G.nodes():
        b = G.nodes[node]["BLACK"]
        w = G.nodes[node]["WHITE"]
        s += abs(b / total_black - w / total_white)
    return 0.5 * s


def compute_metrics(G, state):
    return {
        "half_edge": half_edge(G, state, lam=1.0),
        "moran":     moran_adjacency(G, state),
        "dissimilarity": dissimilarity(G, state),
        "total_black": sum(state[n]["BLACK"] for n in G.nodes()),
        "mean_black_share": np.mean([
            state[n]["BLACK"] / (state[n]["BLACK"] + state[n]["WHITE"])
            for n in G.nodes()
        ]),
    }
