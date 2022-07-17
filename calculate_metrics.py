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


def main(
    filename: str, x_col: str, y_col: str, tot_col: str, headers_only: bool = False
):
    if headers_only:
        print(
            "{filename}, {angle_1_metric}, {angle_2_metric}, {skew_metric}, {edge_0_metric}, {edge_0_5_metric}, {edge_1_metric}, {edge_2_metric}, {edge_10_metric}, {edge_lim_metric}, {half_edge_0_metric}, {half_edge_0_5_metric}, {half_edge_1_metric}, {half_edge_2_metric}, {half_edge_10_metric}, {half_edge_lim_metric}, {dissimilarity_metric}, {frey_metric}, {gini_metric}, {moran_metric}".replace(
                "{", ""
            ).replace(
                "}", ""
            )
        )
        return

    graph = gerrychain.Graph.from_json(filename)
    angle_1_metric = angle_1(graph, x_col, y_col)
    angle_2_metric = angle_2(graph, x_col, y_col)
    skew_metric = skew(graph, x_col, y_col)

    edge_0_metric = edge(graph, x_col, y_col, lam=0)
    edge_0_5_metric = edge(graph, x_col, y_col, lam=0.5)
    edge_1_metric = edge(graph, x_col, y_col, lam=1)
    edge_2_metric = edge(graph, x_col, y_col, lam=2)
    edge_10_metric = edge(graph, x_col, y_col, lam=10)
    edge_lim_metric = edge(graph, x_col, y_col, lam=None)

    half_edge_0_metric = half_edge(graph, x_col, y_col, lam=0)
    half_edge_0_5_metric = half_edge(graph, x_col, y_col, lam=0.5)
    half_edge_1_metric = half_edge(graph, x_col, y_col, lam=1)
    half_edge_2_metric = half_edge(graph, x_col, y_col, lam=2)
    half_edge_10_metric = half_edge(graph, x_col, y_col, lam=10)
    half_edge_lim_metric = half_edge(graph, x_col, y_col, lam=None)

    dissimilarity_metric = dissimilarity(graph, x_col, tot_col)
    frey_metric = frey(graph, x_col, y_col)
    gini_metric = gini(graph, x_col, tot_col)
    moran_metric = moran(graph, x_col)

    print(
        f"{filename}, {angle_1_metric}, {angle_2_metric}, {skew_metric}, {edge_0_metric}, {edge_0_5_metric}, {edge_1_metric}, {edge_2_metric}, {edge_10_metric}, {edge_lim_metric}, {half_edge_0_metric}, {half_edge_0_5_metric}, {half_edge_1_metric}, {half_edge_2_metric}, {half_edge_10_metric}, {half_edge_lim_metric}, {dissimilarity_metric}, {frey_metric}, {gini_metric}, {moran_metric}"
    )


def angle_1(graph: gerrychain.Graph, x_col: str, y_col: str, lam: float = 1) -> float:
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

    if lam == None:
        return first_summation
    else:
        return (lam * first_summation) + second_summation


def angle_2(graph: gerrychain.Graph, x_col: str, y_col: str) -> float:
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

    return 0.5 * (first_summation + second_summation)


def skew(graph: gerrychain.Graph, x_col: str, y_col: str) -> float:
    x_x = angle_1(graph, x_col, x_col)
    x_y = angle_1(graph, x_col, y_col)

    return (x_x) / (x_x + (2 * x_y))


def edge(graph: gerrychain.Graph, x_col: str, y_col: str, lam: float = 1) -> float:
    x_x = angle_1(graph, x_col, x_col, lam=lam)
    x_y = angle_1(graph, x_col, y_col, lam=lam)
    y_y = angle_1(graph, y_col, y_col, lam=lam)

    return 0.5 * ((x_x / (x_x + 2 * x_y)) + (y_y / (y_y + 2 * x_y)))


def half_edge(graph: gerrychain.Graph, x_col: str, y_col: str, lam: float = 1) -> float:
    x_x = angle_1(graph, x_col, x_col, lam=lam)
    x_y = angle_1(graph, x_col, y_col, lam=lam)
    y_y = angle_1(graph, y_col, y_col, lam=lam)

    return 0.5 * ((x_x / (x_x + x_y)) + (y_y / (y_y + x_y)))


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
        for neighbor in graph.neighbors(node):
            summation += abs(
                (int(graph.nodes[node][x_col]) * int(graph.nodes[neighbor][tot_col]))
                - (int(graph.nodes[node][tot_col]) * int(graph.nodes[neighbor][x_col]))
            )

    return (1 / (2 * x_bar * (p_bar - x_bar))) * summation


def moran(graph: gerrychain.Graph, col: str) -> float:
    avg = property_sum(graph, col) / len(graph.nodes())

    top_summation = 0
    bottom_summation = 0
    for node in graph.nodes():
        bottom_summation += (int(graph.nodes[node][col]) - avg) ** 2

        for neighbor in graph.neighbors(node):
            top_summation += (int(graph.nodes[node][col]) - avg) * (
                int(graph.nodes[neighbor][col]) - avg
            )

    return (len(graph.nodes()) / len(graph.edges())) * (
        top_summation / bottom_summation
    )


if __name__ == "__main__":
    typer.run(main)
