"""
This script generates scatter plots of capy and Moran's I versus rho for randomly sampled single-cluster configurations of the 
Iowa county graph, plus a geographic visualization of one such configuration.
Global Parameters:
    RHO: float
        The target group fraction used for the geographic visualization figure
    num_samples: int
        Number of random clustered configurations to sample at each rho value
    num_rhos: int
        Number of evenly spaced rho values between 0.001 and 0.5 to sample over
"""

import sys
import os
import pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
IOWA_SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(IOWA_SCRIPTS))
import capy_core.metrics as metrics
import matplotlib.pyplot as plt
import numpy as np
import gerrychain
import random
import pandas as pd
import typer
from iowa_helpers import visualize_iowa, populate_cluster_random, plot_metric_scatterplots

plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm", #setting to latex font
                    "font.size": 28, "savefig.dpi": 300})

RHO = 0.3
num_samples = 500
num_rhos = 100
def main():
    #loading graph
    g = gerrychain.Graph.from_json("data/experiment_specific/ia_files/ia_counties_2020.json")

    real_rhos = []
    target_rhos = []
    capys = []
    morans =[]

    #generating samples
    rho_grid = np.linspace(.001, .5, num_rhos)
    nodes = list(g.nodes())
    total_pop = metrics.property_sum(g, "TOTPOP")

    for i in range(num_samples):
        rng = random.Random(i)
        for rho in rho_grid:
            target_rhos.append(rho)
            start_node = rng.choice(nodes)
            for node in g.nodes():
                g.nodes[node]["x_pop"] = 0
                g.nodes[node]["y_pop"] = 0
            g_, real_rho = populate_cluster_random(start_node, g, rho * total_pop, rng)
            real_rhos.append(real_rho)
            capys.append(metrics.half_edge(g_, "y_pop", "x_pop"))
            morans.append(metrics.moran(g_, "x_pop", "TOTPOP")["moran_P"])

    fig_moran, ax_moran, fig_capy, ax_capy = plot_metric_scatterplots(real_rhos, capys, morans)

    fig_moran.savefig("figures/iowa/moran_by_rho_onecluster_iowa.png", dpi = 300, bbox_inches="tight")
    fig_capy.savefig("figures/iowa/capy_by_rho_onecluster_iowa.png", dpi = 300, bbox_inches="tight")

    rng = random.Random(42)
    start_node = rng.choice(nodes)
    for node in g.nodes():
        g.nodes[node]["x_pop"] = 0
        g.nodes[node]["y_pop"] = 0
    g_, real_rho = populate_cluster_random(start_node, g, RHO * total_pop, rng)

    fig, ax = visualize_iowa(g_, real_rho)
    base_filename = f"figures/iowa/onecluster_iowa_visualization_rho={real_rho}"
    filestem= base_filename.replace('.', 'p')
    fig.savefig(f"{filestem}.png", dpi = 300, bbox_inches="tight")
    plt.close(fig)

    
    pd.DataFrame({
    "target_rho": target_rhos,
    "real_rho": real_rhos,
    "capy": capys,
    "moran": morans,
    }).to_csv(f"stats/iowa_runs/onecluster_samples_samples={num_samples}_rhos={num_rhos}.csv", index=False)


if __name__ == "__main__":
    typer.run(main)