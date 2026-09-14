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

plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm",
                    "font.size": 11, "savefig.dpi": 300})



def multi_rankr(x_score, y_scores, color_dict, df, name_dict, jitter_x = 0.5, jitter_y = 0.5, label_x=None,  best_fit=True):
    """
    Plot rank-vs-rank scatterplots comparing one x metric against multiple y metrics across CBSAs.

    Each CBSA is ranked independently by x_score and by each column in y_scores. The resulting
    rank pairs are scatter-plotted with optional jitter to reduce overplotting. Multiple y metrics
    appear as separate series on the same axes, colored by color_dict.

    Parameters
    ----------
    x_score : str
        Column name in df to rank CBSAs by on the x-axis.
    y_scores : list of str
        Column names in df to rank CBSAs by on the y-axis; each produces a separate scatter series.
    color_dict : dict
        Maps each y_score column name to a matplotlib color.
    df : pd.DataFrame
        Must contain x_score, all y_scores columns, and a "cbsa_code" column for joining ranks.
    name_dict : dict
        Maps column names to display labels used in the legend.
    jitter_x : float, optional
        Half-width of uniform jitter added to x ranks (default 0.5).
    jitter_y : float, optional
        Half-width of uniform jitter added to y ranks (default 0.5).
    label_x : str or None, optional
        X-axis label override; defaults to x_score if None.
    best_fit : bool, optional
        Reserved parameter; not currently used.
    """

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
            ranks["rank_x"] + np.random.uniform(-jitter_x, jitter_x, size=len(ranks)),
            ranks[rank_col] + np.random.uniform(-jitter_y, jitter_y, size=len(ranks)),
            label=name_dict.get(y_col, y_col),
            alpha=0.7,
            c = color_dict[y_col],
            s = 5
        )
    plt.legend()