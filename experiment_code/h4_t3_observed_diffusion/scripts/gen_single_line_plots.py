import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
import pandas as pd
import geopandas as gpd
from pathlib import Path
from itertools import product

"""
Plots a user determined set of metrics (currently, Moran's I, Dissimilarity, and Sum of Local Moran's I)
over census years for each (city, cluster) pair at a fixed buffer size, with one metric line
per subplot and one figure per cluster. Reads from auto_cluster_metrics.csv.
"""


BUFFER = 4
METRICS = [("moran", "Moran's I"), ("dissimilarity", "Dissimilarity"),
           ("local_moran", "Sum of Local Moran's I of All Nodes in Region")]

tracts = pd.read_csv("data/experiment_specific/observed_diffusion_data/auto_cluster_tracts.csv", dtype={'area_code': str, 'gisjoin': str})
metrics = pd.read_csv("data/experiment_specific/observed_diffusion_data/auto_cluster_metrics.csv", dtype={'area_code': str})
metrics = metrics[metrics["buffer_size"] == BUFFER]

clusters = list(product(["Chicago", "Philadelphia"], ["cluster_1", "cluster_2"]))
colors = plt.cm.tab10.colors

for cluster in clusters:
    cluster_metrics = metrics[(metrics["city_name"] == cluster[0]) & (metrics["cluster"] == cluster[1])]
    fig, ax = plt.subplots(figsize=(8, 6))
    for i, metric in enumerate(METRICS):
        ax.plot(cluster_metrics["year"], cluster_metrics[metric[0]], color=colors[i], marker='o', markersize=4, linewidth=1.5, label = metric[1])
    ax.set_title(f"Metrics over time for {cluster[0]} in {cluster[1]}")
    ax.legend(bbox_to_anchor=(0.5, -.1), loc='upper left', borderaxespad=0)
    plt.tight_layout()
    fig.savefig(f"figures/misc_observed_diffusion_figs/single_lineplots/{cluster[0]}_{cluster[1]}_metrics.png", bbox_inches='tight')
