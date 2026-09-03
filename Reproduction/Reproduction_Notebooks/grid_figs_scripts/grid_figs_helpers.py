import sys, os
sys.path.insert(0, os.path.abspath("../.."))
import pipeline.metrics as metrics
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import gerrychain.grid
import random
from collections import deque
import warnings
random.seed(42)
import seaborn as sns

def populate_ch_grid(G, rho, M, eps): #give graph x and y pop'scripts
    for node in G.graph.nodes:
        if G.graph.nodes[node]["sum"] % 2 == 0:
            if eps == True:
                e_x = random.randint(-5, 5)
                e_y = random.randint(-5, 5)
                G.graph.nodes[node]["x_pop"] = 0
                G.graph.nodes[node]["y_pop"] = M + e_y
            else:
                G.graph.nodes[node]["x_pop"] = 0
                G.graph.nodes[node]["y_pop"] = M
        else:
            if eps == True:
                e_x = random.uniform(-5, 5)
                e_y = random.uniform(-5, 5)
                G.graph.nodes[node]["x_pop"] = 2 * M * rho + 2 + rho * e_x
                G.graph.nodes[node]["y_pop"] = M * (1 - 2* rho) + (1 - 2* rho) *e_y
            else:
                G.graph.nodes[node]["x_pop"] = 2 * M * rho
                G.graph.nodes[node]["y_pop"] = M * (1 - 2* rho) 
    return G #should probably be returning G.graph

def generate_ch_grid(n: int, m: int, rho, M, eps = False):
    G = gerrychain.grid.Grid((n, m))
    for node in G.graph.nodes:
        G.graph.nodes[node]["x"] = node[0]
        G.graph.nodes[node]["y"] = node[1]
        G.graph.nodes[node]["sum"] = node[0] + node[1]
    if eps == True:
        G = populate_ch_grid(G, rho, M, eps = True)
    else:
        G = populate_ch_grid(G, rho, M, eps = False)
    return G

def populate_const_grid(G, rho, M):
    for node in G.graph.nodes:
        G.graph.nodes[node]["x_pop"] = rho * M
        G.graph.nodes[node]["y_pop"] = (1 - rho) * M
    return G

def generate_const_grid(n, m, rho, M):
    G = gerrychain.grid.Grid((n, m))
    for node in G.graph.nodes:
        G.graph.nodes[node]["x"] = node[0]
        G.graph.nodes[node]["y"] = node[1]
        G.graph.nodes[node]["sum"] = node[0] + node[1]
    G = populate_const_grid(G, rho, M)
    return G

def populate_cluster_bfs(start_node, G, M, tot_x_pop):
    # queue for BFS
    queue = deque([start_node])

    visited = set()
    x_pop_sum = 0

    while queue and x_pop_sum < tot_x_pop:
        node = queue.popleft()

        if node in visited or G.graph.nodes[node]["x_pop"] > 0:
            visited.add(node)
            continue
        visited.add(node)

        # assign values
        G.graph.nodes[node]["x_pop"] = M
        G.graph.nodes[node]["y_pop"] = 0

        x_pop_sum += M

        # add neighbors (randomized expansion)
        neighbors = list(G.graph.neighbors(node))
        random.shuffle(neighbors)

        for nbr in neighbors:
            if nbr not in visited:
                queue.append(nbr)
    return G

def populate_cluster_random(start_node, G, M, tot_x_pop):
    # queue for BFS
    queue = deque([start_node])

    visited = set()
    x_pop_sum = 0

    while queue and x_pop_sum < tot_x_pop:
        queue = list(queue)
        random.shuffle(queue)
        queue = deque(queue)
        node = queue.popleft()

        if node in visited or G.graph.nodes[node]["x_pop"] > 0:
            visited.add(node)
            continue
        visited.add(node)

        # assign values
        G.graph.nodes[node]["x_pop"] = M
        G.graph.nodes[node]["y_pop"] = 0

        x_pop_sum += M

        # add neighbors (randomized expansion)
        neighbors = list(G.graph.neighbors(node))
        random.shuffle(neighbors)

        for nbr in neighbors:
            if nbr not in visited:
                queue.append(nbr)
    return G

def generate_clust_grid(n, m, rho, M, method = "bfs"):
    G = gerrychain.grid.Grid((n, m))
    for node in G.graph.nodes:
        G.graph.nodes[node]["x"] = node[0]
        G.graph.nodes[node]["y"] = node[1]
        G.graph.nodes[node]["x_pop"] = 0
        G.graph.nodes[node]["y_pop"] = 0
    x_rand = random.randint(0 , n-1)
    y_rand = random.randint(0 , m-1)
    tot_pop = n * m * M
    tot_x_pop = tot_pop * rho
    start_node = (x_rand, y_rand)    
    if method == "bfs":
        G = populate_cluster_bfs(start_node, G, M, tot_x_pop)
    elif method == "random":
        G = populate_cluster_random(start_node, G, M, tot_x_pop)
    for node in G.graph.nodes():
        if G.graph.nodes[node]["x_pop"] == 0:
            G.graph.nodes[node]["y_pop"] = M
    return G

def generate_isol_grid(n, m, rho, M):
    G = generate_ch_grid(n, m, .5, M)
    nodes = list(G.graph.nodes)
    random.shuffle(nodes)
    current_x_pop = n * m * M * .5
    target_x_pop = n * m * M * rho

    for node in nodes:
        if current_x_pop <= target_x_pop:
            break
        if G.graph.nodes[node]["y_pop"] == 0:
            G.graph.nodes[node]["x_pop"] = 0
            G.graph.nodes[node]["y_pop"] = M
            current_x_pop = current_x_pop - M
    return G

def generate_kclust_grid(n, m, rho, M, k, method = "bfs", blur = True):
    #grid_init
    G = gerrychain.grid.Grid((n, m))
    for node in G.graph.nodes:
        G.graph.nodes[node]["x"] = node[0]
        G.graph.nodes[node]["y"] = node[1]
        G.graph.nodes[node]["x_pop"] = 0
        G.graph.nodes[node]["y_pop"] = 0

    target_nodes = int((rho * n * m) / k)
    seeds = random.sample(list(G.graph.nodes), k)

    # remove seeds = random.sample(...) above the loop

    for i in range(k):
        y_nodes = [node for node in G.graph.nodes() if G.graph.nodes[node]["x_pop"] == 0]
        seed = random.choice(y_nodes)
        if method == "bfs":
            G = populate_cluster_bfs(seed, G, M, target_nodes*M)
        elif method == "random":
            G = populate_cluster_random(seed, G, M, target_nodes*M)

    for node in G.graph.nodes():
        if G.graph.nodes[node]["x_pop"] == 0:
            G.graph.nodes[node]["y_pop"] = M
    
    real_rho = (metrics.property_sum(G.graph, "x_pop") / 
                (metrics.property_sum(G.graph, "x_pop") + 
                 metrics.property_sum(G.graph, "y_pop")))
    
    x_nodes = [
        node for node in G.graph.nodes()
        if G.graph.nodes[node]["x_pop"] > 0
        ]

    H = G.graph.subgraph(x_nodes)

    components = nx.number_connected_components(H)

    return (G, real_rho, components)

def draw_grid_as_checkerboard(G_obj, id, rho, ax=None, title=""):
    """G_obj is the gerrychain GeographicPartition/graph wrapper; G_obj.graph is the nx.Graph."""
    G = G_obj.graph
    nodes = list(G.nodes())
    # gerrychain grid nodes are (col, row) tuples
    cols = [n[0] for n in nodes]
    rows = [n[1] for n in nodes]
    width  = max(cols) + 1
    height = max(rows) + 1

    grid = np.zeros((height, width))
    for n in nodes:
        # 1 if x_pop > 0, 0 if y_pop > 0
        grid[n[1], n[0]] = 1 if G.nodes[n]["x_pop"] > 0 else 0

    if ax is None:
        _, ax = plt.subplots()
    ax.imshow(grid, cmap="bwr", vmin=0, vmax=1, origin="lower",
              interpolation="nearest")
    ax.axis("off")
    plt.savefig(f"Reproduction/Reproduction_Figures/Idealized_Grids/fig-5_{id}_grid_visualization_rho={rho}.png", dpi=150, bbox_inches="tight")
    return ax
