import sys, os
sys.path.insert(0, os.path.abspath("../.."))
os.chdir('/Users/samstephenson/Downloads/capy-bara')



import pipeline.metrics
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import gerrychain.grid
import random
from collections import deque
import warnings
pd.set_option('display.max_columns', None)
from itertools import combinations
from matplotlib.lines import Line2D

black = pd.read_csv("outputs/tracts_in_cbsa_2020-2010-2000-1990-1980_years_march_2020_vintage/white_black.csv")
poc = pd.read_csv("outputs/tracts_in_cbsa_2020-2010-2000-1990-1980_years_march_2020_vintage/white_poc.csv")
poc["year"] = poc["filename"].str.extract(r"(\d{4})").astype(int)
black["year"] = black["filename"].str.extract(r"(\d{4})").astype(int)
black["poc_share"] = black["total_poc"] / (black["total_poc"] + black["total_white"])
black["black_share"] = black["total_black"] / (black["total_black"] + black["total_white"])

poc["poc_share"] = poc["total_poc"] / (poc["total_poc"] + poc["total_white"])
poc["black_share"] = poc["total_black"] / (poc["total_black"] + poc["total_white"])
black["cbsa_code"] = (
    black["filename"]
      .str.extract(r"tracts_in_cbsa_(\d+)")[0]
      .astype(int)
)

poc["cbsa_code"] = (
    poc["filename"]
      .str.extract(r"tracts_in_cbsa_(\d+)")[0]
      .astype(int)
)

name_map_big = {
    14460: "Boston",
    16980: "Chicago",
    19820: "Detroit",
    35620: "NYC",
    29820: "Las Vegas",
}
cities_big = [
    (14460, "Boston"),
    (16980, "Chicago"),
    (19820, "Detroit"),
    (35620, "NYC"),
    (29820, "Las Vegas")
    ]

colors = {
    1990: "#009E73",
    2000: "#E69F00",
    2010: "#D55E00",
}

fig, ax = plt.subplots(figsize=(8, 6))

for city in cities_big:
    city_df = (
        poc[poc["cbsa_code"] == city[0]]
    )
    city_df = (
        city_df[city_df["year"].isin((1990, 2000, 2010))]
        .sort_values("year")
    )

    x = city_df["total_x"]
    y = city_df["half_edge_1"]

    # connect years
    ax.plot(x, y, color="black", lw=1)

    # plot points
    for _, row in city_df.iterrows():
        ax.scatter(
            row["total_x"],
            row["half_edge_1"],
            color=colors[row["year"]],
            s=60,
            zorder=3
        )
    legend_elements = [
        Line2D(
            [0], [0],
            marker='o',
            linestyle='',
            label=str(year),
            markerfacecolor=color,
            markersize=8
        )
        for year, color in colors.items()
    ]
    ax.set_ylabel("Capy")
    ax.set_xlabel("Proportion Black")
    ax.legend(handles=legend_elements, title="Year")

    # label city near first point
    first = city_df.iloc[0]
    ax.annotate(
        city[1],
        (first["total_x"], first["half_edge_1"]),
        xytext=(-10, 10),
        textcoords="offset points",
        fontsize=14
    )
    plt.savefig("Reproduction/Reproduction_Figures/metros_over_time/big_cities")

cities_small = [
    (33340, "Milwaukee"),
    (13820, "Birmingham"),
    (22420, "Flint"),
    (35300, "New Haven"),
    (43780, "South Bend")
    ]

fig, ax = plt.subplots(figsize=(8, 6))

for city in cities_small:
    city_df = (
        poc[poc["cbsa_code"] == city[0]]
    )
    city_df = (
        city_df[city_df["year"].isin((1990, 2000, 2010))]
        .sort_values("year")
    )

    x = city_df["total_x"]
    y = city_df["half_edge_1"]

    # connect years
    ax.plot(x, y, color="black", lw=1)

    # plot points
    for _, row in city_df.iterrows():
        ax.scatter(
            row["total_x"],
            row["half_edge_1"],
            color=colors[row["year"]],
            label = colors[row["year"]],
            s=60,
            zorder=3
        )
    
    for _, row in city_df.iterrows():
        ax.scatter(
            row["total_x"],
            row["half_edge_1"],
            color=colors[row["year"]],
            s=60,
            zorder=3
        )
    legend_elements = [
        Line2D(
            [0], [0],
            marker='o',
            linestyle='',
            label=str(year),
            markerfacecolor=color,
            markersize=8
        )
        for year, color in colors.items()
    ]
    ax.set_ylabel("Capy")
    ax.set_xlabel("Proportion Black")
    ax.legend(handles=legend_elements, title="Year")

    # label city near first point
    first = city_df.iloc[0]
    ax.annotate(
        city[1],
        (first["total_x"], first["half_edge_1"]),
        xytext=(-10, 10),
        textcoords="offset points",
        fontsize=14
    )
    plt.savefig("Reproduction/Reproduction_Figures/metros_over_time/small_cities")