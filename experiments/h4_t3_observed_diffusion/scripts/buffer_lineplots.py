import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
import pandas as pd
import geopandas as gpd
from pathlib import Path
from itertools import product

"""
"""

EXPERIMENT_DIR = EXPERIMENT_DIR = Path(__file__).resolve().parent.parent
METRICS = [("moran", "Moran's I"), ("dissimilarity", "Dissimilarity"),
           ("local_moran", "Sum of Local Moran's I of All Nodes in Region")]

tracts = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_tracts.csv", dtype={'area_code': str, 'gisjoin': str})
metrics = pd.read_csv(EXPERIMENT_DIR / "data" / "auto_cluster_metrics.csv", dtype={'area_code': str})

clusters = list(product(["Chicago", "Philadelphia"], ["cluster_1", "cluster_2"]))
colors = [plt.cm.Blues(0.3 + 0.7 * i / 10) for i in range(11)]

for cluster in clusters:
    cluster_metrics = metrics[(metrics["city_name"] == cluster[0]) & (metrics["cluster"] == cluster[1])]
    for metric in METRICS:
        fig, ax = plt.subplots(figsize=(8, 6))
        if metric[0] != "local_moran":
            ax.plot(cluster_metrics["year"], cluster_metrics[f"city_{metric[0]}"], color="red", marker='o', markersize=4, linewidth=1.5, label = "city wide")
        for i in range(11):
            buffer_metrics = cluster_metrics[cluster_metrics["buffer_size"] == i]
            ax.plot(buffer_metrics["year"], buffer_metrics[metric[0]], color=colors[i], marker='o', markersize=4, linewidth=1.5, label = f"{i}")
        ax.set_title(f"{metric[1]} by Buffer for {cluster[0]} in {cluster[1]}")
        ax.legend(bbox_to_anchor=(1.01, 1), loc='upper left', borderaxespad=0, title = "Buffer Radius")
        plt.tight_layout()
        fig.savefig(EXPERIMENT_DIR / "figures" / f"{cluster[0]}_{cluster[1]}_{metric[1]}_by_buffer.png", bbox_inches='tight')
