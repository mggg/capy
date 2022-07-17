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

def main(filename: str, x_col: str, y_col: str):
    graph = gerrychain.Graph.from_json(filename)
    angle_1_metric = angle_1(graph, x_col, y_col)
    angle_2_metric = angle_2(graph, x_col, y_col)
    print(filename, angle_1_metric, angle_2_metric)

def angle_1(graph: gerrychain.Graph, x_col: str, y_col: str) -> float:
    first_summation = 0
    second_summation = 0
    for node in graph.nodes():
        first_summation += int(graph.nodes[node][x_col]) * int(graph.nodes[node][y_col])

        for neighbor in graph.neighbors(node):
            second_summation += int(graph.nodes[node][x_col]) * int(graph.nodes[neighbor][y_col])
            second_summation += int(graph.nodes[neighbor][x_col]) * int(graph.nodes[node][y_col])

    return first_summation + second_summation

def angle_2(graph: gerrychain.Graph, x_col: str, y_col: str) -> float:
    first_summation = 0
    second_summation = 0
    for node in graph.nodes():
        first_summation += int(graph.nodes[node][x_col]) * int(graph.nodes[node][y_col]) - ((int(graph.nodes[node][x_col]) + int(graph.nodes[node][y_col])) * 0.5)

        for neighbor in graph.neighbors(node):
            second_summation += int(graph.nodes[node][x_col]) * int(graph.nodes[neighbor][y_col])
            second_summation += int(graph.nodes[neighbor][x_col]) * int(graph.nodes[node][y_col])

    return 0.5 * (first_summation + second_summation)

if __name__ == "__main__":
    typer.run(main)
