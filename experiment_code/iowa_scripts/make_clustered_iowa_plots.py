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
import math
import typer
from iowa_helpers import visualize_iowa, populate_cluster_random
random.seed(42)

plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm", #setting to latex font
                    "font.size": 28, "savefig.dpi": 300})

RHO = 0.3
num_samples = 500
num_rhos = 100
def main():
    #loading graph
    g = gerrychain.Graph.from_json("data/experiment_specific/ia_files/ia_counties_2020.json")

    real_rhos = []
    capys = []
    morans =[]

    #generating samples
    rho_grid = np.linspace(.001, .5, num_rhos)
    nodes = list(g.nodes())
    total_pop = metrics.property_sum(g, "TOTPOP")

    for _ in range(num_samples):
        for rho in rho_grid:
            seed = random.choice(nodes)
            for node in g.nodes():
                g.nodes[node]["x_pop"] = 0
                g.nodes[node]["y_pop"] = 0
            g_, real_rho = populate_cluster_random(seed, g, rho * total_pop)
            real_rhos.append(real_rho)
            capys.append(metrics.half_edge(g_, "y_pop", "x_pop"))
            morans.append(metrics.moran(g_, "x_pop", "TOTPOP")["moran_P"])

    #setting axis ticks
    rho_step = 0.1
    xmin = math.floor(min(real_rhos) / rho_step) * rho_step
    xmax = math.ceil(max(real_rhos) / rho_step) * rho_step

    moran_step = 0.2
    moran_ymin = math.floor(min(morans) / moran_step) * moran_step
    moran_ymax = math.ceil(max(morans) / moran_step) * moran_step

    capy_step = 0.1
    capy_ymin = math.floor(min(capys) / capy_step) * capy_step
    capy_ymax = math.ceil(max(capys) / capy_step) * capy_step

    #plotting
    plt.figure(figsize=(10, 10))
    plt.scatter(real_rhos, morans, s=0.1, color = "#1560bd")
    plt.xticks(np.arange(xmin, xmax + rho_step/2, rho_step))
    plt.xlim(xmin, xmax)
    plt.yticks(np.arange(moran_ymin, moran_ymax + moran_step/2, moran_step))
    plt.ylim(moran_ymin-0.02, moran_ymax)
    plt.tight_layout()
    plt.savefig("figures/iowa/moran_by_rho_onecluster_iowa.png", dpi = 300, bbox_inches="tight")

    plt.figure(figsize=(10, 10))
    plt.scatter(real_rhos, capys, s=0.1, color = "#1560bd")
    plt.xticks(np.arange(xmin, xmax + rho_step/2, rho_step))
    plt.xlim(xmin, xmax)
    plt.yticks(np.arange(capy_ymin, capy_ymax + capy_step/2, capy_step))
    plt.ylim(capy_ymin-0.02, capy_ymax)
    plt.tight_layout()
    plt.savefig("figures/iowa/capy_by_rho_onecluster_iowa.png", dpi = 300, bbox_inches="tight")

    g_, real_rho = populate_cluster_random(seed, g, RHO* metrics.property_sum(g, "TOTPOP"))
    fig, ax = visualize_iowa(g_, real_rho)
    base_filename = f"figures/iowa/onecluster_iowa_visualization_rho={real_rho}"
    filestem= base_filename.replace('.', 'p')
    fig.savefig(f"{filestem}.png", dpi = 300, bbox_inches="tight")
    plt.close(fig)

if __name__ == "__main__":
    typer.run(main)