"""
Theoretical graph constructors and seed-cluster definitions for H4 T2.

Each constructor returns a plain networkx.Graph with integer node labels.
`seed_clusters(G, graph_type)` returns a dict mapping position-name to
a list of node IDs that form the starting cluster.
"""

import networkx as nx
import numpy as np


# ── Constructors ──────────────────────────────────────────────────────────────

def make_grid(rows=12, cols=12):
    G = nx.grid_2d_graph(rows, cols)
    G = nx.convert_node_labels_to_integers(G, label_attribute="grid_pos")
    return G


def make_ring(n=60):
    return nx.cycle_graph(n)


def make_star(n_leaves=30):
    # hub = node 0, leaves = 1..n_leaves
    return nx.star_graph(n_leaves)


def make_barbell(clique_size=10, bridge_len=6):
    # two complete graphs of clique_size connected by a path of bridge_len nodes
    return nx.barbell_graph(clique_size, bridge_len)


def make_hex_lattice(rows=7, cols=7):
    G = nx.hexagonal_lattice_graph(rows, cols)
    G = nx.convert_node_labels_to_integers(G, label_attribute="hex_pos")
    return G


def make_triangular_lattice(rows=9, cols=9):
    G = nx.triangular_lattice_graph(rows, cols)
    G = nx.convert_node_labels_to_integers(G, label_attribute="tri_pos")
    return G


# ── Seed-cluster helpers ──────────────────────────────────────────────────────

def _bfs_ball(G, root, radius):
    """Return all nodes within `radius` hops of `root`."""
    lengths = nx.single_source_shortest_path_length(G, root, cutoff=radius)
    return list(lengths.keys())


def _most_central(G):
    """Node with the highest closeness centrality (or min eccentricity)."""
    ecc = nx.eccentricity(G)
    return min(ecc, key=ecc.get)


def _most_peripheral(G):
    """Node farthest from the graph center (max eccentricity, then max degree)."""
    ecc = nx.eccentricity(G)
    max_ecc = max(ecc.values())
    candidates = [n for n, e in ecc.items() if e == max_ecc]
    return max(candidates, key=lambda n: G.degree(n))


def seed_clusters(G, graph_type, cluster_radius=2):
    """
    Return {position_name: [node_ids]} for several natural starting positions.
    cluster_radius controls the BFS ball size for the seed.
    """
    clusters = {}

    if graph_type == "grid":
        # grid_pos stored as attribute during construction
        pos_map = {G.nodes[n]["grid_pos"]: n for n in G.nodes()}
        rows = max(r for r, c in pos_map) + 1
        cols = max(c for r, c in pos_map) + 1
        cr, cc = rows // 2, cols // 2

        center_node = pos_map[(cr, cc)]
        corner_node = pos_map[(0, 0)]
        edge_node   = pos_map[(cr, 0)]  # midpoint of left edge

        clusters["center"] = _bfs_ball(G, center_node, cluster_radius)
        clusters["corner"] = _bfs_ball(G, corner_node, cluster_radius)
        clusters["edge"]   = _bfs_ball(G, edge_node,   cluster_radius)

    elif graph_type == "ring":
        n = G.number_of_nodes()
        # All positions equivalent by symmetry; use one and a "spread" version
        clusters["contiguous"] = list(range(cluster_radius * 2 + 1))
        # Spread: nodes evenly spaced, no single contiguous block
        spread_size = cluster_radius * 2 + 1
        step = n // spread_size
        clusters["spread"] = [i * step % n for i in range(spread_size)]

    elif graph_type == "star":
        # hub = 0; seed starting at hub vs. starting at periphery leaves
        clusters["hub_center"] = [0] + list(range(1, cluster_radius + 2))
        clusters["leaves_only"] = list(range(1, cluster_radius * 2 + 2))

    elif graph_type == "barbell":
        # barbell_graph: left clique is 0..m-1, path is m..m+k-1, right is m+k..2m+k-1
        m = G.graph.get("clique_size", None)
        # Infer clique size from graph structure: max clique
        cliques = sorted(nx.find_cliques(G), key=len, reverse=True)
        left_clique  = sorted(cliques[0])
        right_clique = sorted(cliques[1])
        all_nodes    = set(G.nodes())
        bridge       = sorted(all_nodes - set(left_clique) - set(right_clique))

        clusters["left_clique"]  = left_clique
        clusters["right_clique"] = right_clique
        if bridge:
            clusters["bridge_midpoint"] = _bfs_ball(G, bridge[len(bridge) // 2], cluster_radius)

    elif graph_type in ("hex", "triangular"):
        center = _most_central(G)
        periphery = _most_peripheral(G)
        clusters["center"]     = _bfs_ball(G, center,    cluster_radius)
        clusters["periphery"]  = _bfs_ball(G, periphery, cluster_radius)

    return clusters


# ── Catalogue used by run_experiment ─────────────────────────────────────────

GRAPH_CATALOGUE = [
    ("grid",        make_grid,              dict()),
    ("ring",        make_ring,              dict()),
    ("star",        make_star,              dict()),
    ("barbell",     make_barbell,           dict()),
    ("hex",         make_hex_lattice,       dict()),
    ("triangular",  make_triangular_lattice, dict()),
]
