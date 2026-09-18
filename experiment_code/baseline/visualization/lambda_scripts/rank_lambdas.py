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

plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm", #setting to latex font
                    "font.size": 11, "savefig.dpi": 300})

"""
This script generates rank-rank scatter plots comparing how CBSAs are ordered by half_edge at lambda=1 versus other lambda values, for the top 100 most populous areas.
Global Parameters:
    COMPARISON: str
        Comparison group for the segregation metric — "black" compares white vs. Black residents, "poc" compares white vs. all people of color
    GEOGRAPHY: str
        Geographic unit of analysis — "tracts", "block_groups", or "blocks"
    AREA_TYPE: str
        Definition of the metro area — "cbsa" uses the full CBSA boundary, "max_city" uses the principal city
    YEAR: int
        Census year to filter on (e.g. 2020)
    JITTER_X: float
        Horizontal jitter applied to scatter points to reduce overplotting
    JITTER_Y: float
        Vertical jitter applied to scatter points to reduce overplotting
    WEIGHTS: str
        Controls which lambda values are plotted — "small" plots only lambda=0 and lambda=inf, "full" plots lambda=0, 0.5, 2, 10, and inf
"""
plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm",
                    "font.size": 11, "savefig.dpi": 300})

COMPARISON = "black" #"black" or "poc"
GEOGRAPHY = "tracts" #"tracts", "block_groups", or "blocks"
AREA_TYPE = "cbsa"  #"cbsa" or "max_city"
YEAR = 2020
JITTER_X = 0
JITTER_Y = 0.3
WEIGHTS = "small" #small or full

#MAKE THIS A PREPROCESSING SCRIPT AND PUT IT IN THE DATA THING
area_df = pd.read_csv(f"data/shared/outputs//{GEOGRAPHY}_in_{AREA_TYPE}/white_{COMPARISON}.csv")
area_df["year"] = area_df["filename"].str.extract(r"(\d{4})").astype(int)
area_df["cbsa_code"] = (
    area_df["filename"]
      .str.extract(rf"{GEOGRAPHY}_in_{AREA_TYPE}_(\d+)")[0]
      .astype(int)
)

df_2020 = area_df[area_df["year"] == YEAR]
df_2020 = df_2020.sort_values("total_population", ascending = False)
top_100 = df_2020.head(100)

weights_he_small = ["half_edge_0", 
        "half_edge_lim"]

color_dict_small = {"half_edge_0" :"#d11a42", 
        "half_edge_lim" : "#1560bd"
        }

name_dict_small = {"half_edge_0" : r"$\lambda = 0$", 
        "half_edge_lim" : r"$\lambda = \infty$"
        }

weights_he = ["half_edge_0", 
        "half_edge_0.5", 
        "half_edge_2", 
        "half_edge_10",
        "half_edge_lim",]

color_dict = {"half_edge_0" :"#d11a42", 
        "half_edge_0.5" : "#ffa812", 
        "half_edge_2" : "#006b3c", 
        "half_edge_10" : "#69359c",
        "half_edge_lim" : "#1560bd",}

name_dict = {"half_edge_0" : r"$\lambda = 0$", 
        "half_edge_0.5" : r"$\lambda = 0.5$", 
        "half_edge_2" : r"$\lambda = 2$", 
        "half_edge_10" : r"$\lambda = 10$",
        "half_edge_lim" : r"$\lambda = \infty$",} 

if WEIGHTS == "full":
        multi_rankr("half_edge_1", weights_he, color_dict, top_100, name_dict, jitter_x= JITTER_X, jitter_y = JITTER_Y)
if WEIGHTS == "small":
        multi_rankr("half_edge_1", weights_he_small, color_dict_small, top_100, name_dict_small, jitter_x= JITTER_X, jitter_y = JITTER_Y)
        #adding diagonal line
        n = len(top_100)
        plt.plot([1, n], [1, n], color="black", linestyle="--", linewidth=1, zorder=0)

handles, labels = plt.gca().get_legend_handles_labels()
plt.legend().remove()

os.makedirs("figures/baseline/lambda_rankings", exist_ok=True)
base_file_name = f"figures/baseline/lambda_rankings/{GEOGRAPHY}_in_{AREA_TYPE}_{WEIGHTS}_lambda_rankings_whitev{COMPARISON}_weightedyvcapyx_lineplot_in_{YEAR}_with_{JITTER_X}{JITTER_Y}jitter_mainplot"
file_stem = base_file_name.replace('.', 'p')
plt.savefig(file_stem, dpi = 300, bbox_inches = "tight")

legend_fig, legend_ax = plt.subplots()
legend_ax.axis("off")
leg = legend_ax.legend(handles, labels, loc="center",
                 fontsize=8, handletextpad=0.4, borderpad=0.4,
                 edgecolor="black", fancybox=False)
legend_fig.canvas.draw()

from matplotlib.transforms import Bbox
bbox = leg.get_window_extent().transformed(legend_fig.dpi_scale_trans.inverted())
padded = Bbox([[bbox.x0 - 0.05, bbox.y0 - 0.05],
               [bbox.x1 + 0.05, bbox.y1 + 0.05]])

base_file_name = f"figures/baseline/lambda_rankings/{GEOGRAPHY}_in_{AREA_TYPE}_{WEIGHTS}_lambda_rankings_whitev{COMPARISON}_weightedyvcapyx_lineplot_in_{YEAR}_with_{JITTER_X}{JITTER_Y}jitter_legend"
file_stem = base_file_name.replace('.', 'p')
plt.savefig(file_stem, dpi=300, bbox_inches=padded)
