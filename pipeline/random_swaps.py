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
import secrets


def main(filename: str, output_dir: str, rounds=1000):
    attrs = ["WHITE", "BLACK", "AMIN", "ASIAN", "2MORE", "TOTPOP", "POC"]

    graph = gerrychain.Graph.from_json(filename)

    if len(graph.nodes) < 2:
        return

    prefix = filename.split("/")[-1].split(".")[0] + "_swap_"
    for i in range(int(rounds)):
        first_node = 0
        second_node = 0
        while first_node == second_node:
            first_node = secrets.choice(list(graph.nodes))
            second_node = secrets.choice(list(graph.nodes))

        first_node_attrs = {x: graph.nodes[first_node][x] for x in attrs}
        second_node_attrs = {x: graph.nodes[second_node][x] for x in attrs}

        for attr in attrs:
            graph.nodes[first_node][attr] = second_node_attrs[attr]
            graph.nodes[second_node][attr] = first_node_attrs[attr]

        graph.to_json(output_dir + prefix + str(i) + ".json")


if __name__ == "__main__":
    typer.run(main)
