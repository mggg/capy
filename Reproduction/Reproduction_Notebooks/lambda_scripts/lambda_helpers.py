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


def multi_rankr(x_score, y_scores, color_dict, df, name_dict, jitter_amount=0.5, label_x=None,  best_fit=True):


    if label_x is None:
        label_x = x_score

    x = (
        df[[x_score, "cbsa_code"]]
        .sort_values(x_score)
        .reset_index(drop=True)
    )

    x["rank_x"] = np.arange(1, len(x) + 1)

    for y_col in y_scores:

        y_df = (
            df[[y_col, "cbsa_code"]]
            .sort_values(y_col)
            .reset_index(drop=True)
        )

        rank_col = f"rank_{y_col}"

        y_df[rank_col] = np.arange(1, len(y_df) + 1)

        ranks = x[["cbsa_code", "rank_x"]].merge(
            y_df[["cbsa_code", rank_col]],
            on="cbsa_code"
        )
        
        plt.scatter(
            ranks["rank_x"],
            ranks[rank_col] + np.random.uniform(-jitter_amount, jitter_amount, size=len(ranks)),
            label=name_dict.get(y_col, y_col),
            alpha=0.7,
            c = color_dict[y_col],
            s = 5
        )

    plt.xlabel("Rank by CAPY")
    plt.ylabel("Rank by Weighted CAPY")
    plt.legend()