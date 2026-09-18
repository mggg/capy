"""
This script generates three figures for a uniform Iowa county graph: a capy-vs-rho lineplot, a geographic visualization of county-level rho values, and a standalone diverging colorbar.
Global Parameters:
    RHO: float
        The uniform group fraction used for the geographic visualization and colorbar figures
    num_rhos: int
        Number of evenly spaced values of rho to be used in the scatterplot.
"""

import sys
import os
import pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
IOWA_SCRIPTS = pathlib.Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(IOWA_SCRIPTS))
import capy_core.metrics as metrics
import matplotlib.pyplot as plt
import numpy as np
import random
import gerrychain
from iowa_helpers import  visualize_iowa
import typer
random.seed(42)

plt.rcParams.update({"font.family": "serif", "mathtext.fontset": "cm", #setting to latex font
                    "font.size": 28, "savefig.dpi": 300})

RHO = 0.3
num_rhos = 50
def main():
    #making plots
    graph = gerrychain.Graph.from_json("data/experiment_specific/ia_files/ia_counties_2020.json")

    fig, ax = plot_rho_vs_capy_uniform(graph, num_rhos)
    fig.savefig("figures/iowa/capy_by_rho_uniform_iowa.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    fig, ax = visualize_iowa(make_uniform_iowa(graph, RHO), RHO)
    base_filename = f"figures/iowa/uniform_iowa_visualization_rho={RHO}"
    filestem = base_filename.replace('.', 'p')
    fig.savefig(f"{filestem}.png", dpi = 300, bbox_inches="tight")
    plt.close(fig)

def make_uniform_iowa(graph, rho):
    """
    Assigns x_pop and y_pop to every node so that each county's group fraction equals rho uniformly.
    Parameters:
        graph: nx.Graph
            County adjacency graph with node attribute TOTPOP
        rho: float
            The uniform group fraction to assign to every node
    """

    for node in graph.nodes():
        graph.nodes[node]["x_pop"] = rho * graph.nodes[node]['TOTPOP']
        graph.nodes[node]["y_pop"]  = (1-rho) * graph.nodes[node]['TOTPOP']
    return graph

def plot_rho_vs_capy_uniform(graph, num_rhos):
    """
    Plots half_edge capy versus rho for a uniform Iowa graph across 50 evenly spaced rho values between 0.001 and 0.5.
    Parameters:
        graph: nx.Graph
            County adjacency graph with node attribute TOTPOP; copied and modified for each rho value
    """
    rhos = np.linspace(0.001,0.5, num_rhos)

    # data lists for scores
    capys = np.zeros(num_rhos)

    for i in range(num_rhos):
        g1 = graph.copy()
        g1 = make_uniform_iowa(g1, rhos[i])
        capys[i] = metrics.half_edge(g1, "x_pop", "y_pop")

    fig, ax = plt.subplots(figsize=(10, 10))   # add this
    ax.scatter(rhos, capys, s=1, color="#1560bd")  # plt. → ax.
    ax.set_xlim([0, 0.5])
    ax.set_ylim([0, 1])
    fig.tight_layout()

    return fig, ax

if __name__ == "__main__":
    typer.run(main)