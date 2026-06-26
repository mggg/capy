import geopandas as gpd
import typer
import os
import glob
import gerrychain
import networkx as nx
import matplotlib.pyplot as plt
from itertools import product
import tqdm
import functools
import sys
import scipy.sparse
import numpy as np
import traceback

def main(
    filename: str, x_col: str, y_col: str, tot_col: str, headers_only: bool = False
):
    try:
        run_metrics(filename, x_col, y_col, tot_col, headers_only)
    except ZeroDivisionError as e:
        with open("outputs/metric_failures.csv", "a+") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() == 0:
                print("filename,cbsa_code,error", file=f)
            print(f"{filename},{os.path.basename(filename).split('_')[1]},{e}", file=f)
        print(filename, e, file=sys.stderr)







def run_metrics(
    filename: str, x_col: str, y_col: str, tot_col: str, headers_only: bool = False
):
    graph = gerrychain.Graph.from_json(filename)

    capy_metrics = {}
    capy_metrics["filename"] = filename
    capy_metrics["x_col"] = x_col
    capy_metrics["y_col"] = y_col
    capy_metrics["tot_col"] = tot_col
    capy_metrics["angle_1"] = angle_1(graph, x_col, y_col)
    capy_metrics["angle_2"] = angle_2(graph, x_col, y_col) #rationale seems to be to cache these for the later calculations?
    
    e_assort, he_assort = assortativity(graph, x_col, y_col)
    capy_metrics["e_assort"] = e_assort
    capy_metrics["he_assort"] = he_assort


    for lam in [0, 0.5, 1, 2, 10, None]: 
        lam_str = "lim" if lam is None else str(lam)
        capy_metrics[f"skew_self_{lam_str}"] = skew(graph, x_col, y_col, lam = lam)
        capy_metrics[f"skew_other_{lam_str}"] = skew(graph, y_col, x_col, lam = lam)
        capy_metrics[f"edge_{lam_str}"] = 0.5 * (capy_metrics[f"skew_other_{lam_str}"] + 
                                                 capy_metrics[f"skew_self_{lam_str}"])

        capy_metrics[f"skew'_self_{lam_str}"] = skew_prime(graph, x_col, y_col, lam = lam)
        capy_metrics[f"skew'_other_{lam_str}"] = skew_prime(graph, y_col, x_col, lam = lam)
        capy_metrics[f"half_edge_{lam_str}"] = 0.5 * (capy_metrics[f"skew'_other_{lam_str}"] + 
                                                 capy_metrics[f"skew'_self_{lam_str}"])    


        capy_metrics[f"skew_self_exact_{lam_str}"] = skew(graph, x_col, y_col, lam = lam)
        capy_metrics[f"skew_other_exact_{lam_str}"] = skew(graph, y_col, x_col, lam = lam)
        capy_metrics[f"edge_exact_{lam_str}"] = 0.5 * (capy_metrics[f"skew_other_exact_{lam_str}"] + 
                                                 capy_metrics[f"skew_self_exact_{lam_str}"])

        capy_metrics[f"skew'_self_exact_{lam_str}"] = skew_prime(graph, x_col, y_col, lam = lam)
        capy_metrics[f"skew'_other_exact_{lam_str}"] = skew_prime(graph, y_col, x_col, lam = lam)
        capy_metrics[f"half_edge_exact_{lam_str}"] = 0.5 * (capy_metrics[f"skew'_other_exact_{lam_str}"] + 
                                                 capy_metrics[f"skew'_self_exact_{lam_str}"])

    for p in [1, 2, 10]:
        string = str(p)
        capy_metrics[f"dissimilarity_{string}"] = dissimilarity(graph, x_col, y_col, p)


    capy_metrics["frey"] = frey(graph, x_col, y_col)
    capy_metrics["gini"] = gini(graph, x_col, y_col)
    capy_metrics["moran_A"] = moran(graph, x_col, tot_col)["moran_A"]
    capy_metrics["moran_P"] = moran(graph, x_col, tot_col)["moran_P"]
    capy_metrics["moran_L"] = moran(graph, x_col, tot_col)["moran_L"]
    capy_metrics["moran_M"] = moran(graph, x_col, tot_col)["moran_M"]

    capy_metrics["total_population"] = property_sum(graph, "TOTPOP")
    capy_metrics["total_white"] = property_sum(graph, "WHITE")
    capy_metrics["total_poc"] = property_sum(graph, "POC")
    capy_metrics["total_black"] = property_sum(graph, "BLACK")
    capy_metrics["total_asian"] = property_sum(graph, "ASIAN")
    capy_metrics["total_amin"] = property_sum(graph, "AMIN")
    capy_metrics["total_x"] = property_sum(graph, x_col) / property_sum(graph, "TOTPOP")
    capy_metrics["total_y"] = property_sum(graph, y_col) / property_sum(graph, "TOTPOP")

    capy_metrics["total_nodes"] = len(graph.nodes())
    capy_metrics["total_edges"] = len(graph.edges())

    capy_metrics_keys = ",".join(map(str, list(capy_metrics.keys())))
    capy_metrics_values = ",".join(map(str, list(capy_metrics.values())))

    if headers_only:
        print(capy_metrics_keys)
    else:
        print(capy_metrics_values)


def angle_1(graph: gerrychain.Graph, x_col: str, y_col: str, lam: float = 1) -> float:
    """
    This implements `<x_col, y_col>` from the paper
    """
    first_summation, second_summation = _angle_1(graph, x_col, y_col)

    if lam == None:
        return first_summation
    else:
        return (lam * first_summation) + second_summation


@functools.cache  # cached for speed purposes
def _angle_1(graph: gerrychain.Graph, x_col: str, y_col: str) -> float:
    first_summation = 0
    second_summation = 0
    for node in graph.nodes():
        first_summation += int(graph.nodes[node][x_col]) * int(graph.nodes[node][y_col])

    for node, neighbor in graph.edges():
        second_summation += int(graph.nodes[node][x_col]) * int(
            graph.nodes[neighbor][y_col])
        second_summation += int(graph.nodes[neighbor][x_col]) * int(
            graph.nodes[node][y_col])

    # wrong? old version below counts each undirected edge twice because every neighbor pair
    # is visited once from each endpoint.
    # for node in graph.nodes():
    #     for neighbor in graph.neighbors(node):
    #         second_summation += int(graph.nodes[node][x_col]) * int(
    #             graph.nodes[neighbor][y_col]
    #         )
    #         second_summation += int(graph.nodes[neighbor][x_col]) * int(
    #             graph.nodes[node][y_col]
    #         )

    return (first_summation, second_summation)


def angle_2(graph: gerrychain.Graph, x_col: str, y_col: str, lam: float = 1) -> float:
    """
    This implements `<<x_col, y_col>>` from the paper
    """
    first_summation, second_summation = _angle_2(graph, x_col, y_col)

    if lam == None:
        return first_summation
    else:
        return 0.5 * ((lam * first_summation) + second_summation)


@functools.cache
def _angle_2(graph: gerrychain.Graph, x_col: str, y_col: str, lam: float = 1) -> float:
    first_summation = 0
    second_summation = 0
    for node in graph.nodes():
        first_summation += int(graph.nodes[node][x_col]) * int(
            graph.nodes[node][y_col]
        ) - ((int(graph.nodes[node][x_col]) + int(graph.nodes[node][y_col])) * 0.5)

    for node, neighbor in graph.edges():
        second_summation += int(graph.nodes[node][x_col]) * int(
            graph.nodes[neighbor][y_col])
        second_summation += int(graph.nodes[neighbor][x_col]) * int(
            graph.nodes[node][y_col])

    # wrong? old version below counts each undirected edge twice because every neighbor pair
    # is visited once from each endpoint.
    # for node in graph.nodes():
    #     for neighbor in graph.neighbors(node):
    #         second_summation += int(graph.nodes[node][x_col]) * int(
    #             graph.nodes[neighbor][y_col]
    #         )
    #         second_summation += int(graph.nodes[neighbor][x_col]) * int(
    #             graph.nodes[node][y_col]
    #         )

    return (first_summation, second_summation)


def skew(graph: gerrychain.Graph, x_col: str, y_col: str, lam: float = 1) -> float:
    x_x = angle_1(graph, x_col, x_col, lam = lam)
    x_y = angle_1(graph, x_col, y_col, lam = lam)

    return (x_x) / (x_x + (2 * x_y))

def skew_prime(graph: gerrychain.Graph, x_col: str, y_col: str, lam: float = 1) -> float:
    x_x = angle_1(graph, x_col, x_col, lam = lam)
    x_y = angle_1(graph, x_col, y_col, lam = lam)

    return (x_x) / (x_x + (x_y))

def skew_exact(graph: gerrychain.Graph, x_col: str, y_col: str, lam: float = 1) -> float:
    x_x = angle_2(graph, x_col, x_col, lam = lam)
    x_y = angle_1(graph, x_col, y_col, lam = lam)

    return (x_x) / (x_x + (x_y))

def skew_prime_exact(graph: gerrychain.Graph, x_col: str, y_col: str, lam: float = 1) -> float:
    x_x = angle_2(graph, x_col, x_col, lam = lam)
    x_y = angle_1(graph, x_col, y_col, lam = lam)

    return (2 * x_x) / ( 2 * x_x + (x_y))

def edge(
    graph: gerrychain.Graph, x_col: str, y_col: str, lam: float = 1, func=angle_1
) -> float:
    x_x = func(graph, x_col, x_col, lam=lam)
    x_y = func(graph, x_col, y_col, lam=lam)
    y_y = func(graph, y_col, y_col, lam=lam)

    return 0.5 * ((x_x / (x_x + 2 * x_y)) + (y_y / (y_y + 2 * x_y)))


def half_edge(
    graph: gerrychain.Graph, x_col: str, y_col: str, lam: float = 1, func=angle_1
) -> float:
    x_x = func(graph, x_col, x_col, lam=lam)
    x_y = func(graph, x_col, y_col, lam=lam)
    y_y = func(graph, y_col, y_col, lam=lam)

    return 0.5 * ((x_x / (x_x + x_y)) + (y_y / (y_y + x_y)))

def assortativity(graph: gerrychain.Graph, x_col: str, y_col: str):
    #determine node majorities
    for node in graph.nodes():
        threshold = (graph.nodes[node][x_col] + graph.nodes[node][y_col]) / 2
        if graph.nodes[node][x_col] >= threshold: #so ties break in favor of x_col
            graph.nodes[node]["x_maj"] = 1
            graph.nodes[node]["y_maj"] = 0
        else: 
            graph.nodes[node]["x_maj"] = 0
            graph.nodes[node]["y_maj"] = 1
    
    #calculating E, He assortativity scores
    try:
        e_assort = 0.5 * (
            skew_exact(graph, "x_maj", "y_maj", 0) + #zero lambdas strictly speaking superfluous
            skew_exact(graph, "y_maj", "x_maj", 0)
        )
    except ZeroDivisionError: #if there are no x majority units, then <<x,x>> = ,x,y. = <<x,x>> + <x,y> = 0
        e_assort = np.nan

    try:
        he_assort = 0.5 * (
            skew_prime_exact(graph, "x_maj", "y_maj", 0) +
            skew_prime_exact(graph, "y_maj", "x_maj", 0)
        )
    except ZeroDivisionError:
        he_assort = np.nan
    return e_assort, he_assort

@functools.cache
def property_sum(graph: gerrychain.Graph, col: str) -> float:
    cummulative = 0
    for node in graph.nodes():
        cummulative += int(graph.nodes[node][col])
    return cummulative


def dissimilarity(graph: gerrychain.Graph, x_col: str, y_col: str, p: float) -> float:
    x_bar = property_sum(graph, x_col)
    p_bar = x_bar + property_sum(graph, y_col)

    summation = 0
    for node in graph.nodes():
        node_total = int(graph.nodes[node][x_col]) + int(graph.nodes[node][y_col])
        summation += abs(
            (int(graph.nodes[node][x_col]) * p_bar)
            - (node_total * x_bar)
        ) ** (p)

    return (1 / ((2 ** (1 / p)) * (x_bar * (p_bar - x_bar)))) * (summation ** (1 / p))


def frey(graph: gerrychain.Graph, x_col: str, y_col: str) -> float:
    x_bar = property_sum(graph, x_col)
    y_bar = property_sum(graph, y_col)

    summation = 0
    for node in graph.nodes():
        summation += abs(
            (int(graph.nodes[node][x_col]) * y_bar)
            - (int(graph.nodes[node][y_col]) * x_bar)
        )

    return (1 / (2 * x_bar * y_bar)) * summation


def gini(graph: gerrychain.Graph, x_col: str, y_col: str) -> float:
    x_bar = property_sum(graph, x_col)
    p_bar = x_bar + property_sum(graph, y_col)

    summation = 0
    for node in graph.nodes():
        node_total = int(graph.nodes[node][x_col]) + int(graph.nodes[node][y_col])
        for other_node in graph.nodes():
            other_node_total = int(graph.nodes[other_node][x_col]) + int(
                graph.nodes[other_node][y_col]
            )
            summation += abs(
                (int(graph.nodes[node][x_col]) * other_node_total)
                - (
                    node_total
                    * int(graph.nodes[other_node][x_col])
                )
            )

    return (1 / (2 * x_bar * (p_bar - x_bar))) * summation


def make_adj_weights(graph: gerrychain.Graph):
    #TODO: check_order
    nodes = list(graph.nodes())
    A = nx.adjacency_matrix(graph, nodelist=nodes).tocsr()
    degrees = np.array([graph.degree(n) for n in nodes])    
    D = scipy.sparse.diags(degrees)

    inv_degrees = np.zeros_like(degrees, dtype=float)
    mask = degrees > 0
    inv_degrees[mask] = 1 / degrees[mask]
    D_inv = scipy.sparse.diags(inv_degrees)

    P = D_inv @ A
    L = D - A

    A_coo = A.tocoo()
    rows = A_coo.row
    cols = A_coo.col

    vals = 1 / np.maximum(degrees[rows], degrees[cols])

    M = scipy.sparse.csr_matrix((vals, (rows, cols)), shape=A.shape)

    diag = 1 - np.asarray(M.sum(axis=1)).ravel()
    M = M + scipy.sparse.diags(diag)

    return A, P, L, M

def moran(graph: gerrychain.Graph, x_col: str, tot_col: str) -> float:
    shares = np.array([
        graph.nodes[node][x_col] / graph.nodes[node][tot_col]
        for node in graph.nodes()
        ])

    shares -= shares.mean()

    x = scipy.sparse.csr_matrix(shares).T

    weights = make_adj_weights(graph)
    names = ["A", "P", "L", "M"]

    morans = {}

    for name, W in zip(names, weights):
        numerator = (x.T @ W @ x)[0, 0]
        denominator = (x.T @ x)[0, 0]
        S0 = W.sum()
        if name == "L": #Laplacians are considered self normalized so no division by S0, (for them S0 == 0)
            S0 = 1
            
        morans[f"moran_{name}"] = (len(graph) / S0) * numerator / denominator

    return morans


if __name__ == "__main__":
    typer.run(main)
