import sys, os
sys.path.insert(0, os.path.abspath("../.."))
import capy_core.metrics as metrics
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
from matplotlib.colors import ListedColormap

####CHANGE RHO TO TARGET RHO
def populate_ch_grid(graph, rho, node_pop, eps): #give graph x and y pop'scripts
    """
    Assign checkerboard x_pop/y_pop populations to an existing gerrychain Grid.

    Nodes where (x_coordinate + y_coordinate) is even receive only y_pop; nodes where (x + y) is odd
    receive x_pop = 2*node_pop*rho and y_pop = node_pop*(1 - 2*rho). With eps=True, small
    uniform random noise is added to each assignment.

    Parameters
    ----------
    graph : gerrychain.grid.Grid
        Grid whose nodes already have "x" and "y" coordinate attributes.
    rho : float
        Target global fraction of x_pop.
    node_pop : int or float
        Base population per node.
    eps : bool
        If True, add random noise to population assignments.

    Returns
    -------
    gerrychain.grid.Grid
    """

    for node in graph.graph.nodes:
        if graph.graph.nodes[node]["sum"] % 2 == 0:
            if eps == True:
                e_x = random.randint(-5, 5)
                e_y = random.randint(-5, 5)
                graph.graph.nodes[node]["x_pop"] = 0
                graph.graph.nodes[node]["y_pop"] = node_pop + e_y
            else:
                graph.graph.nodes[node]["x_pop"] = 0
                graph.graph.nodes[node]["y_pop"] = node_pop
        else:
            if eps == True:
                e_x = random.uniform(-5, 5)
                e_y = random.uniform(-5, 5)
                graph.graph.nodes[node]["x_pop"] = 2 * node_pop * rho + 2 + rho * e_x
                graph.graph.nodes[node]["y_pop"] = node_pop * (1 - 2* rho) + (1 - 2* rho) *e_y
            else:
                graph.graph.nodes[node]["x_pop"] = 2 * node_pop * rho
                graph.graph.nodes[node]["y_pop"] = node_pop * (1 - 2* rho) 
    return graph

def generate_ch_grid(num_columns: int, num_rows: int, rho, node_pop, eps = False):
    """
    Create and populate an n×m gerrychain Grid in a checkerboard pattern.

    Parameters
    ----------
    num_columns, num_rows : int
        Grid dimensions (columns × rows).
    rho : float
        Target global fraction of x_pop.
    node_pop : int or float
        Base population per node.
    eps : bool
        If True, add random noise to population assignments.

    Returns
    -------
    gerrychain.grid.Grid
    """

    G = gerrychain.grid.Grid((num_columns, num_rows))
    for node in G.graph.nodes:
        G.graph.nodes[node]["x"] = node[0]
        G.graph.nodes[node]["y"] = node[1]
        G.graph.nodes[node]["sum"] = node[0] + node[1]
    if eps == True:
        G = populate_ch_grid(G, rho, node_pop, eps = True)
    else:
        G = populate_ch_grid(G, rho, node_pop, eps = False)
    return G

def populate_const_grid(graph, rho, node_pop):
    """
    Assign uniform x_pop/y_pop to every node: x_pop = rho*node_pop, y_pop = (1-rho)*node_pop.

    Parameters
    ----------
    graph : gerrychain.grid.Grid
    rho : float
        Target global fraction of x_pop.
    node_pop : int or float
        Population per node.

    Returns
    -------
    gerrychain.grid.Grid
    """

    for node in graph.graph.nodes:
        graph.graph.nodes[node]["x_pop"] = rho * node_pop
        graph.graph.nodes[node]["y_pop"] = (1 - rho) * node_pop
    return graph

def generate_const_grid(num_columns, num_rows, rho, node_pop):
    """
    Create an n×m gerrychain Grid with uniform population at every node.

    Parameters
    ----------
    num_columns, num_rows : int
        Grid dimensions (columns × rows).
    rho : float
        Target global fraction of x_pop.
    node_pop : int or float
        Population per node.

    Returns
    -------
    gerrychain.grid.Grid
    """

    G = gerrychain.grid.Grid((num_columns, num_rows))
    for node in G.graph.nodes:
        G.graph.nodes[node]["x"] = node[0]
        G.graph.nodes[node]["y"] = node[1]
        G.graph.nodes[node]["sum"] = node[0] + node[1]
    G = populate_const_grid(G, rho, node_pop)
    return G

def populate_cluster_bfs(start_node, graph, node_pop, target_x_pop):
    """
    Fill a contiguous cluster of x_pop nodes via BFS from start_node.

    Expands outward in BFS order (neighbors shuffled for randomness) until the
    cumulative x_pop reaches target_x_pop. Skips nodes already assigned x_pop > 0.

    Parameters
    ----------
    start_node : tuple
        (col, row) seed node for the cluster.
    graph : gerrychain.grid.Grid
    node_pop : int or float
        Population assigned to each node in the cluster (x_pop=node_pop, y_pop=0).
    target_x_pop : float
        Target total x_pop for the cluster.

    Returns
    -------
    gerrychain.grid.Grid
    """

    # queue for BFS
    queue = deque([start_node])

    visited = set()
    x_pop_sum = 0

    while queue and x_pop_sum < target_x_pop:
        node = queue.popleft()

        if node in visited or graph.graph.nodes[node]["x_pop"] > 0:
            visited.add(node)
            continue
        visited.add(node)

        # assign values
        graph.graph.nodes[node]["x_pop"] = node_pop
        graph.graph.nodes[node]["y_pop"] = 0

        x_pop_sum += node_pop

        # add neighbors (randomized expansion)
        neighbors = list(graph.graph.neighbors(node))
        random.shuffle(neighbors)

        for nbr in neighbors:
            if nbr not in visited:
                queue.append(nbr)
    return graph

def populate_cluster_random(start_node, graph, node_pop, target_x_pop):
    """
    Fill a contiguous cluster of x_pop nodes via randomized frontier expansion.

    Like populate_cluster_bfs but shuffles the entire frontier queue each step,
    producing less compact, more jagged cluster shapes.

    Parameters
    ----------
    start_node : tuple
        (col, row) seed node for the cluster.
    graph : gerrychain.grid.Grid
    node_pop : int or float
        Population assigned to each node in the cluster (x_pop=node_pop, y_pop=0).
    target_x_pop : float
        Target total x_pop for the cluster.

    Returns
    -------
    gerrychain.grid.Grid
    """

    queue = deque([start_node])

    visited = set()
    x_pop_sum = 0

    while queue and x_pop_sum < target_x_pop:
        queue = list(queue)
        random.shuffle(queue)
        queue = deque(queue)
        node = queue.popleft()

        if node in visited or graph.graph.nodes[node]["x_pop"] > 0:
            visited.add(node)
            continue
        visited.add(node)

        # assign values
        graph.graph.nodes[node]["x_pop"] = node_pop
        graph.graph.nodes[node]["y_pop"] = 0

        x_pop_sum += node_pop

        # add neighbors (randomized expansion)
        neighbors = list(graph.graph.neighbors(node))
        random.shuffle(neighbors)

        for nbr in neighbors:
            if nbr not in visited:
                queue.append(nbr)
    return graph

def generate_clust_grid(num_columns, num_rows, rho, node_pop, method = "bfs"):
    """
    Create an n×m gerrychain Grid with a single contiguous x_pop cluster.

    The cluster seed is chosen at random; all remaining nodes receive y_pop=node_pop.

    Parameters
    ----------
    num_columns, num_rows : int
        Grid dimensions (columns × rows).
    rho : float
        Target fraction of nodes in the x_pop cluster.
    node_pop : int or float
        Population per node.
    method : {"bfs", "random"}
        Cluster expansion strategy passed to populate_cluster_bfs or
        populate_cluster_random.

    Returns
    -------
    gerrychain.grid.Grid
    """

    G = gerrychain.grid.Grid((num_columns, num_rows))
    for node in G.graph.nodes:
        G.graph.nodes[node]["x"] = node[0]
        G.graph.nodes[node]["y"] = node[1]
        G.graph.nodes[node]["x_pop"] = 0
        G.graph.nodes[node]["y_pop"] = 0
    x_rand = random.randint(0 , num_columns-1)
    y_rand = random.randint(0 , num_rows-1)
    tot_pop = num_columns * num_rows * node_pop
    tot_x_pop = tot_pop * rho
    start_node = (x_rand, y_rand)    
    if method == "bfs":
        G = populate_cluster_bfs(start_node, G, node_pop, tot_x_pop)
    elif method == "random":
        G = populate_cluster_random(start_node, G, node_pop, tot_x_pop)
    for node in G.graph.nodes():
        if G.graph.nodes[node]["x_pop"] == 0:
            G.graph.nodes[node]["y_pop"] = node_pop
    return G

def generate_isol_grid(num_columns, num_rows, rho, node_pop):
    """
    Create an n×m gerrychain Grid with maximally isolated (scattered) x_pop nodes.

    Starts from a checkerboard at rho=0.5, then randomly converts x_pop nodes to
    y_pop nodes until the target rho is reached.

    Parameters
    ----------
    num_columns, num_rows : int
        Grid dimensions (columns × rows).
    rho : float
        Target global fraction of x_pop (must be <= 0.5).
    node_pop : int or float
        Population per node.

    Returns
    -------
    gerrychain.grid.Grid
    """

    G = generate_ch_grid(num_columns, num_rows, .5, node_pop)
    nodes = list(G.graph.nodes)
    random.shuffle(nodes)
    current_x_pop = num_columns * num_rows * node_pop * .5
    target_x_pop = num_columns * num_rows * node_pop * rho

    for node in nodes:
        if current_x_pop <= target_x_pop:
            break
        if G.graph.nodes[node]["y_pop"] == 0:
            G.graph.nodes[node]["x_pop"] = 0
            G.graph.nodes[node]["y_pop"] = node_pop
            current_x_pop = current_x_pop - node_pop
    return G

def generate_kclust_grid(num_columns, num_rows, target_rho, node_pop, num_seeds, method = "bfs", blur = True):
    """
    Create an n×m gerrychain Grid with k contiguous x_pop clusters.

    Seeds are chosen from unoccupied nodes at the start of each cluster's
    expansion. All remaining nodes receive y_pop=node_pop.

    Parameters
    ----------
    num_columns, num_rows : int
        Grid dimensions (columns × rows).
    target_rho : float
        Target global fraction of x_pop, split evenly across k clusters.
        The realized rho returned may differ due to integer node counts.
    node_pop : int or float
        Population per node.
    k : int
        Number of clusters.
    method : {"bfs", "random"}
        Cluster expansion strategy.
    blur : bool
        Reserved for future use; currently has no effect.

    Returns
    -------
    tuple of (gerrychain.grid.Grid, float, int)
        The populated grid, the realized global rho, and the number of connected
        x_pop components (may exceed k if clusters merge or split).
    """

    G = gerrychain.grid.Grid((num_columns, num_rows))
    for node in G.graph.nodes:
        G.graph.nodes[node]["x"] = node[0]
        G.graph.nodes[node]["y"] = node[1]
        G.graph.nodes[node]["x_pop"] = 0
        G.graph.nodes[node]["y_pop"] = 0

    target_nodes = int((target_rho * num_columns * num_rows) / num_seeds)

    for i in range(num_seeds):
        y_nodes = [node for node in G.graph.nodes() if G.graph.nodes[node]["x_pop"] == 0]
        seed = random.choice(y_nodes)
        if method == "bfs":
            G = populate_cluster_bfs(seed, G, node_pop, target_nodes*node_pop)
        elif method == "random":
            G = populate_cluster_random(seed, G, node_pop, target_nodes*node_pop)

    for node in G.graph.nodes():
        if G.graph.nodes[node]["x_pop"] == 0:
            G.graph.nodes[node]["y_pop"] = node_pop
    
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

def draw_grid_as_checkerboard(graph, id, rho, ax=None, title=""):
    """
    Render a gerrychain Grid as a two-color image showing x_pop vs y_pop nodes.

    Parameters
    ----------
    graph : gerrychain.grid.Grid
        GerryChain wrapper; graph.graph is the underlying nx.Graph.
    id : str
        Identifier used in the output filename.
    rho : float
        Global rho value used in the output filename.
    ax : matplotlib.axes.Axes, optional
        Axes to draw on; a new figure is created if None.
    title : str, optional
        Unused; reserved for future labeling.

    Returns
    -------
    matplotlib.axes.Axes
    """

    G = graph.graph
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
    cmap = ListedColormap(["#FFA812", "#006B3C"])
    ax.imshow(grid, cmap=cmap, vmin=0, vmax=1, origin="lower", interpolation="nearest")

    ax.axis("off")
    plt.savefig(f"figures/idealized_grids/fig-5_{id}_grid_visualization_rho={rho}.png", dpi=150, bbox_inches="tight")
    return ax
