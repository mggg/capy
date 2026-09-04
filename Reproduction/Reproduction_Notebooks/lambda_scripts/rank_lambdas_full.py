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
import sys, os

sys.path.insert(0, os.path.dirname(__file__))  # lambda_scripts dir

from matplotlib.lines import Line2D
from lambda_helpers import multi_rankr

COMPARISON = "black" #"black" or "poc"
GEOGRAPHY = "tracts" #"tracts", "block_groups", or "blocks"
AREA_TYPE = "cbsa"  #"cbsa" or "max_city"
YEAR = 2020
JITTER_X = 0.5
JITTER_Y = 0.5

#MAKE THIS A PREPROCESSING SCRIPT AND PUT IT IN THE DATA THING
area_df = pd.read_csv(f"outputs/{GEOGRAPHY}_in_{AREA_TYPE}/white_{COMPARISON}.csv")
area_df["year"] = area_df["filename"].str.extract(r"(\d{4})").astype(int)
area_df["cbsa_code"] = (
    area_df["filename"]
      .str.extract(rf"tracts_in_{AREA_TYPE}_(\d+)")[0]
      .astype(int)
)


df_2020 = area_df[area_df["year"] == YEAR]
df_2020 = df_2020.sort_values("total_population", ascending = False)
top_100 = df_2020.head(100)

weights_he = ["half_edge_0", 
        "half_edge_lim",
        "half_edge_0.5", 
        "half_edge_2", 
        "half_edge_10",]

color_dict = {"half_edge_0" :"#d11a42", 
        "half_edge_lim" : "#1560bd",
        "half_edge_0.5" : "#ffa812", 
        "half_edge_2" : "#006b3c", 
        "half_edge_10" : "#69359c",}

name_dict = {"half_edge_0" : r"$\lambda = 0$", 
        "half_edge_lim" : r"$\lambda = \infty$",
        "half_edge_0.5" : r"$\lambda = 0.5$", 
        "half_edge_2" : r"$\lambda = 2$", 
        "half_edge_10" : r"$\lambda = 10$",} 

multi_rankr("half_edge_1", weights_he, color_dict, top_100, name_dict, jitter_x= JITTER_X, jitter_y = JITTER_Y)

plt.savefig(f"Reproduction/Reproduction_Figures/lambda_rankings/{GEOGRAPHY}_in_{AREA_TYPE}_small_lambda_rankings_whitev{COMPARISON}_in_{YEAR}_with_({JITTER_X, JITTER_Y})jitter.png", dpi = 300, bbox_inches = "tight")