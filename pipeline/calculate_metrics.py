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


def main(
    filename: str, x_col: str, y_col: str, tot_col: str, headers_only: bool = False
):
    try:
        run_metrics(filename, x_col, y_col, tot_col, headers_only)
    except ZeroDivisionError as e:
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
    capy_metrics["angle_2"] = angle_2(graph, x_col, y_col)
    capy_metrics["skew"] = skew(graph, x_col, y_col)

    for lam in [0, 0.5, 1, 2, 10, None]:
        for fname, func in [("angle_1", angle_1), ("angle_2", angle_2)]:
            for vname, variant in [("edge", edge), ("half_edge", half_edge)]:
                metric_name = f"{vname}_lam_{str(lam).replace('.','_').replace('None','lim')}_{fname}"
                capy_metrics[metric_name] = variant(
                    graph, x_col, y_col, lam=lam, func=func
                )

    capy_metrics["dissimilarity"] = dissimilarity(graph, x_col, tot_col)
    capy_metrics["frey"] = frey(graph, x_col, y_col)
    capy_metrics["gini"] = gini(graph, x_col, tot_col)
    capy_metrics["moran"] = moran(graph, x_col, tot_col)

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

        for neighbor in graph.neighbors(node):
            second_summation += int(graph.nodes[node][x_col]) * int(
                graph.nodes[neighbor][y_col]
            )
            second_summation += int(graph.nodes[neighbor][x_col]) * int(
                graph.nodes[node][y_col]
            )

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

        for neighbor in graph.neighbors(node):
            second_summation += int(graph.nodes[node][x_col]) * int(
                graph.nodes[neighbor][y_col]
            )
            second_summation += int(graph.nodes[neighbor][x_col]) * int(
                graph.nodes[node][y_col]
            )

    return (first_summation, second_summation)


def skew(graph: gerrychain.Graph, x_col: str, y_col: str) -> float:
    x_x = angle_1(graph, x_col, x_col)
    x_y = angle_1(graph, x_col, y_col)

    return (x_x) / (x_x + (2 * x_y))


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


@functools.cache
def property_sum(graph: gerrychain.Graph, col: str) -> float:
    cummulative = 0
    for node in graph.nodes():
        cummulative += int(graph.nodes[node][col])
    return cummulative


def dissimilarity(graph: gerrychain.Graph, x_col: str, tot_col: str) -> float:
    x_bar = property_sum(graph, x_col)
    p_bar = property_sum(graph, tot_col)

    summation = 0
    for node in graph.nodes():
        summation += abs(
            (int(graph.nodes[node][x_col]) * p_bar)
            - (int(graph.nodes[node][tot_col]) * x_bar)
        )

    return (1 / (2 * x_bar * (p_bar - x_bar))) * summation


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


def gini(graph: gerrychain.Graph, x_col: str, tot_col: str) -> float:
    x_bar = property_sum(graph, x_col)
    p_bar = property_sum(graph, tot_col)

    summation = 0
    for node in graph.nodes():
        for other_node in graph.nodes():
            summation += abs(
                (int(graph.nodes[node][x_col]) * int(graph.nodes[other_node][tot_col]))
                - (
                    int(graph.nodes[node][tot_col])
                    * int(graph.nodes[other_node][x_col])
                )
            )

    return (1 / (2 * x_bar * (p_bar - x_bar))) * summation


def moran(graph: gerrychain.Graph, x_col: str, tot_col: str) -> float:
    # TODO: double/triple-check the 2 coefficient
    total_shares = []
    for node in graph.nodes():
        total_shares.append(
            int(graph.nodes[node][x_col]) / int(graph.nodes[node][tot_col])
        )
    avg = sum(total_shares) / len(total_shares)

    top_summation = 0
    bottom_summation = 0
    for node in graph.nodes():
        node_share = int(graph.nodes[node][x_col]) / int(graph.nodes[node][tot_col])
        bottom_summation += (node_share - avg) ** 2

        for neighbor in graph.neighbors(node):
            neighbor_share = int(graph.nodes[neighbor][x_col]) / int(
                graph.nodes[neighbor][tot_col]
            )
            top_summation += (node_share - avg) * (neighbor_share - avg)

    return (
        (len(graph.nodes()) / len(graph.edges()))
        * (top_summation / bottom_summation)
        * 0.5
    )


if __name__ == "__main__":
    typer.run(main)
