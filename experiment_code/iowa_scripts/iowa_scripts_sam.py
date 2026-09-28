import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pathlib
import capy_core.metrics as metrics
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
import random
import math
import gerrychain
from collections import deque
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
import matplotlib.patches as mpatches
from experiment_code.iowa_scripts.iowa_helpers import visualize_iowa

def populate_cluster_random(start_node, graph, target_x_pop, rng):
    """
    Assigns x_pop via random cluster growth expansion from a seed node until the total x_pop reaches 
    target_x_pop, then sets y_pop as the remainder for every node.

    Parameters:
        start_node: int
            The seed node from which random cluster growth expansion begins
        graph: nx.Graph
            County adjacency graph with node attribute TOTPOP; modified in place
        target_x_pop: float
            The total x_pop at which random cluster growth stops adding nodes to the cluster
        rng: random.Random
            Local RNG instance passed through to each populate_cluster_random call
    Returns:
        graph: nx.Graph
            The modified graph with x_pop and y_pop set on every node
        real_rho: float
            The actual achieved global group fraction, which may exceed the target due to discrete node assignments
    """
    
    queue = deque([start_node])

    visited = set()
    x_pop_sum = 0

    while queue and x_pop_sum < target_x_pop:
        queue = list(queue)
        rng.shuffle(queue)
        queue = deque(queue)
        node = queue.popleft()

        if node in visited or graph.nodes[node]["x_pop"] > 0:
            visited.add(node)
            continue
        visited.add(node)

        # assign values
        graph.nodes[node]["x_pop"] = graph.nodes[node]["TOTPOP"]
        graph.nodes[node]["y_pop"] = 0

        x_pop_sum += graph.nodes[node]["TOTPOP"]

        # add neighbors (randomized expansion)
        neighbors = list(graph.neighbors(node))
        rng.shuffle(neighbors)

        for nbr in neighbors:
            if nbr not in visited:
                queue.append(nbr)


    for node in graph.nodes():
        if graph.nodes[node]["x_pop"] == 0:
            graph.nodes[node]["y_pop"] = graph.nodes[node]["TOTPOP"]

    real_rho = metrics.property_sum(graph, "x_pop")/metrics.property_sum(graph, "TOTPOP")
    
    return graph, real_rho

def generate_clustered_grid(graph, target_rho, num_start_nodes, rng):
    """
    Builds a clustered configuration, defined as a configuration where all counties are either 
    all group x or all group y, and the subgraph of the x counties has less or equal to k components.
    The function works by growing num_start_nodes independent random cluster growth clusters, 
    each targeting an equal share of the total x_pop budget, then computes 
    the achieved rho and number of connected components. Clusters from different
    start nodes can merge into one another, sometimes leading to only a single cluster.
    Parameters:
        graph: nx.Graph
            County adjacency graph with node attributes TOTPOP, x_pop, and y_pop; modified in place
        target_rho: float
            Target global group fraction to distribute across num_start_nodes clusters
        num_start_nodes: int
            Number of clusters to grow. Clusters can merge into one another
        rng: random.Random
            Local RNG instance passed through to each populate_cluster_random call
    Returns:
        G: nx.Graph
            The modified graph with x_pop and y_pop set on every node
        real_rho: float
            The actual achieved global group fraction across all clusters
        components: int
            Number of connected components among the x_pop-carrying nodes
    """
    for node in graph.nodes():
        graph.nodes[node]["x_pop"] = 0
        graph.nodes[node]["y_pop"] = 0

    target_pop = target_rho * metrics.property_sum(graph, "TOTPOP") / num_start_nodes

    for _ in range(num_start_nodes):
        y_nodes = [node for node in graph.nodes if graph.nodes[node]["x_pop"] == 0]
        if y_nodes == []:
            return None
        start_node = rng.choice(y_nodes)

        G, cluster_rho = populate_cluster_random(start_node, graph, target_pop, rng)

    for node in G.nodes():
        if G.nodes[node]["x_pop"] == 0:
            G.nodes[node]["y_pop"] = graph.nodes[node]["TOTPOP"]
    
    real_rho = (metrics.property_sum(G, "x_pop") / 
                (metrics.property_sum(G, "x_pop") + 
                metrics.property_sum(G, "y_pop")))
    
    x_nodes = [
        node for node in G.nodes()
        if G.nodes[node]["x_pop"] > 0
        ]

    H = G.subgraph(x_nodes)

    components = nx.number_connected_components(H)

    return G, real_rho, components

def make_random_iowa(graph, rng, target_x_pop):
    """
    Makes a unifromly random Iowa cluster by shuffling the nodes into a random order and assigning them all 
    xpop until the target rho is reached. The remaining nodes are assigned to be all ypop.
    """
    for node in graph.nodes():
        graph.nodes[node]["x_pop"] = 0
        graph.nodes[node]["y_pop"] = 0
    nodelist = [node for node in graph.nodes()]
    rng.shuffle(nodelist)
    tot_x_pop = 0
    for node in nodelist:
        if tot_x_pop < target_x_pop:
            graph.nodes[node]["x_pop"] = graph.nodes[node]["TOTPOP"]
            graph.nodes[node]["y_pop"] = 0
            tot_x_pop += graph.nodes[node]["TOTPOP"]
        else:
            break
    for node in nodelist:
        if graph.nodes[node]["x_pop"] == 0:
            graph.nodes[node]["x_pop"] = 0
            graph.nodes[node]["y_pop"] = graph.nodes[node]["TOTPOP"]
    real_rho = (metrics.property_sum(graph, "x_pop") / 
            (metrics.property_sum(graph, "x_pop") + 
            metrics.property_sum(graph, "y_pop")))
    
    return graph, real_rho

def valid_isolated_config(graph, column):
    """
    Checks whether the x_pop-carrying nodes in the graph form a valid isolated configuration, where every nonzero node is its own connected component (no two selected nodes are adjacent).
    Parameters:
        graph: nx.Graph
            County adjacency graph with node attribute specified by column
        column: str
            Name of the node attribute to check for nonzero values
    Returns:
        bool
            True if the nonzero nodes form a valid isolated configuration, False otherwise
    """

    nodes_in_cluster = []
    
    for node in graph.nodes():
        if graph.nodes[node][column] >0:
            nodes_in_cluster.append(node)
    
    # should have as many connected components as there are nonzero entries
    subgraph = graph.subgraph(nodes_in_cluster)
    return subgraph.number_of_edges() == 0


def make_random_isolated_config(graph, target_rho, rng):
    """
    Randomly assigns x_pop to a greedy independent set of nodes until the global group fraction reaches rho, then sets y_pop as the remainder for every node.
    Parameters:
        graph: nx.Graph
            County adjacency graph with node attribute TOTPOP; modified in place
        rho: float
            Target global group fraction; assignment stops once this value is reached or exceeded
        rng: random.Random
            Local RNG to shuffle node order
    Returns:
        graph: nx.Graph
            The modified graph with x_pop and y_pop set on every node
        real_rho: float
    The actual achieved global group fraction. May exceed target_rho if the last selected node overshoots, or fall short of target_rho if the 
    maximal independent set is exhausted before the target is reached.
    """

    # reset populations
    for node in graph.nodes():
        graph.nodes[node]["x_pop"] = 0
        graph.nodes[node]["y_pop"] = graph.nodes[node]["TOTPOP"]

    blocked = set()

    nodes = list(graph.nodes())
    rng.shuffle(nodes)

    total_pop =  metrics.property_sum(graph, "TOTPOP")
    x_pop = 0
    for node in nodes:
        if node in blocked:
            continue

        blocked.add(node)
        blocked.update(graph.neighbors(node))

        graph.nodes[node]["x_pop"] = graph.nodes[node]["TOTPOP"]
        x_pop+=graph.nodes[node]["x_pop"]
        graph.nodes[node]["y_pop"] = 0

        current_rho = x_pop / total_pop
        if current_rho >= target_rho:
            break

    for node in graph.nodes():
        graph.nodes[node]["y_pop"] = graph.nodes[node]["TOTPOP"] - graph.nodes[node]["x_pop"]

    return graph, metrics.property_sum(graph, "x_pop") / metrics.property_sum(graph, "TOTPOP")

#Plotting Iowa Visualizations
g = gerrychain.Graph.from_json("data/experiment_specific/ia_files/ia_counties_2020.json")
rng = random.Random(42)

g_random , real_rho_random  = make_random_iowa(g.copy(), rng, 0.3 * metrics.property_sum(g, "TOTPOP"))
g_clustered, real_rho_clustered, components = generate_clustered_grid(g.copy(), 0.3, 3, rng)
g_isolated, real_rho_isolated = make_random_isolated_config(g.copy(), 0.3, rng)

fig, ax = visualize_iowa(g_random, real_rho_random)
fig.savefig(f"figures/iowa_prototypes/random_iowa_rho={real_rho_random}.png", dpi=300, bbox_inches="tight")
fig, ax = visualize_iowa(g_isolated, real_rho_isolated)
fig.savefig(f"figures/iowa_prototypes/isol_iowa_rho={real_rho_isolated}.png", dpi=300, bbox_inches="tight")
fig, ax = visualize_iowa(g_clustered, real_rho_clustered)
fig.savefig(f"figures/iowa_prototypes/isol_iowa_rho={real_rho_clustered}.png", dpi=300, bbox_inches="tight")

#Plotting Iowa Scatterplots
g = gerrychain.Graph.from_json("data/experiment_specific/ia_files/ia_counties_2020.json")
num_rhos = 50
num_samples = 100

real_rhos_isol = []
real_rhos_clust = []
real_rhos_random = []
target_rhos = []
capys_isol = []
morans_isol =[]
capys_clust = []
morans_clust =[]
capys_random = []
morans_random =[]

#generating samples
rho_grid = np.linspace(.001, .5, num_rhos)
nodes = list(g.nodes())
total_pop = metrics.property_sum(g, "TOTPOP")

for i in range(num_samples):
    rng = random.Random(i)
    for rho in rho_grid:
        target_rhos.append(rho)
        start_node = rng.choice(nodes)
        for node in g.nodes():
            g.nodes[node]["x_pop"] = 0
            g.nodes[node]["y_pop"] = 0
        
        g_ , real_rho_  = make_random_iowa(g.copy(), rng, rho * metrics.property_sum(g, "TOTPOP"))
        real_rhos_random.append(real_rho_)
        capys_random.append(metrics.half_edge(g_, "y_pop", "x_pop"))
        morans_random.append(metrics.moran(g_, "x_pop", "TOTPOP")["moran_P"])    

        g__, real_rho__, components = generate_clustered_grid(g.copy(), rho, 1, rng)
        real_rhos_clust.append(real_rho__)
        capys_clust.append(metrics.half_edge(g__, "y_pop", "x_pop"))
        morans_clust.append(metrics.moran(g__, "x_pop", "TOTPOP")["moran_P"])   

        g___, real_rho___ = make_random_isolated_config(g.copy(), rho, rng)
        real_rhos_isol.append(real_rho___)
        capys_isol.append(metrics.half_edge(g___, "y_pop", "x_pop"))
        morans_isol.append(metrics.moran(g___, "x_pop", "TOTPOP")["moran_P"])

#plotting moran scatterplot
fig, ax = plt.subplots()
all_points = (
    [(x, y, "#006B3C", "random")    for x, y in zip(real_rhos_random, morans_random)] +
    [(x, y, "#d11a42", "clustered") for x, y in zip(real_rhos_clust,  morans_clust)]  +
    [(x, y, "#69359c", "isolated")  for x, y in zip(real_rhos_isol,   morans_isol)]
)

random.shuffle(all_points)
xs, ys, colors, _ = zip(*all_points)
ax.scatter(xs, ys, c=colors, s=0.2)

ax.legend(handles=[
    mpatches.Patch(color="#006B3C", label="Random"),
    mpatches.Patch(color="#d11a42", label="Clustered"),
    mpatches.Patch(color="#69359c", label="Isolated"),
])
ax.set_title("Moran's I on Idealized Iowa Configurations")
ax.set_ylabel("Moran's I")
ax.set_xlabel(r"$\rho$")
ax.set_ylim(-1.05, 1)
ax.set_yticks(np.arange(-1, 1.01, 0.5))

fig.savefig("figures/iowa_prototypes/iowa_colored_pointcloud_moran.png", dpi=300, bbox_inches="tight")

#plotting capy scatterplot
fig, ax = plt.subplots()
all_points = (
    [(x, y, "#006B3C", "random")    for x, y in zip(real_rhos_random, capys_random)] +
    [(x, y, "#d11a42", "clustered") for x, y in zip(real_rhos_clust,  capys_clust)]  +
    [(x, y, "#69359c", "isolated")  for x, y in zip(real_rhos_isol,   capys_isol)]
)
random.shuffle(all_points)
xs, ys, colors, _ = zip(*all_points)
ax.scatter(xs, ys, c=colors, s=0.2)

ax.legend(handles=[
    mpatches.Patch(color="#006B3C", label="Random"),
    mpatches.Patch(color="#d11a42", label="Clustered"),
    mpatches.Patch(color="#69359c", label="Isolated"),
])
ax.set_title("Capy on Idealized Iowa Configurations")
ax.set_ylabel("Capy")
ax.set_xlabel(r"$\rho$")
ax.set_ylim(-0.05, 1)
ax.set_yticks(np.arange(0, 1.01, 0.25))

fig.savefig("figures/iowa_prototypes/iowa_colored_pointcloud_capy.png", dpi=300, bbox_inches="tight")