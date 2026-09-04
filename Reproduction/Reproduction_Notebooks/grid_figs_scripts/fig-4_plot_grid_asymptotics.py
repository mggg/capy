import sys, os
import matplotlib.pyplot as plt
import numpy as np

def edge_a_ch(rho):
    return (25-50 * rho + 20 * rho ** 2 - 4 * rho ** 3) / (2 * (5 - rho) * (5 - 2 * rho ** 2))

def half_edge_a_ch(rho):
    return (5 - 8 * rho) / (2 * (5 - 5 * rho))

def edge_a_isol(rho):
    return (25 - 41 * rho) / (9 * (5 - rho))

def half_edge_a_isol(rho):
    return (3 - 5 * rho) / (5 - 5 * rho)

def edge_a_const(rho):
    return (1 - rho + rho ** 2) / (2 + rho + rho ** 2)

def half_edge_a_const(rho):
    return .5

def edge_a_one_clust(rho):
    return 1

def half_edge_a_one_clust(rho):
    return 1

#asymptotic graph for edge
isol = []
ch = []
const = []
one_clust = []

x = np.linspace(.01, .5, 20)

for rho in x:
    isol.append(edge_a_isol(rho))
    ch.append(edge_a_ch(rho))
    const.append(edge_a_const(rho))
    one_clust.append(edge_a_one_clust(rho))

plt.plot(x, isol, label="Isolated")
plt.plot(x, ch, label="Checkerboard")
plt.plot(x, const, label="Constant")
plt.plot(x, one_clust, label="One Cluster")

plt.legend(fontsize=8, handlelength=1.5, handleheight=.75, handletextpad=0.4, borderpad=0.4)
plt.xlabel("Minority Proportion")
plt.ylabel("Edge")
plt.savefig("Reproduction/Reproduction_Figures/Idealized_Grids/fig-4_grid_asymptotics_edge.png", dpi=150, bbox_inches="tight")
plt.close()


#asymptotic graph for half edge
isol = []
ch = []
const = []
one_clust = []

x = np.linspace(.01, .5, 20)

for rho in x:
    isol.append(half_edge_a_isol(rho))
    ch.append(half_edge_a_ch(rho))
    const.append(half_edge_a_const(rho))
    one_clust.append(half_edge_a_one_clust(rho))

plt.plot(x, isol, label="Isolated")
plt.plot(x, ch, label="Checkerboard")
plt.plot(x, const, label="Constant")
plt.plot(x, one_clust, label="One Cluster")

plt.legend(fontsize=8, handlelength=1.5, handleheight=.75, handletextpad=0.4, borderpad=0.4)

plt.xlabel("Minority Proportion")
plt.ylabel("Capy")
plt.savefig("Reproduction/Reproduction_Figures/Idealized_Grids/fig-4_grid_asymptotics_half_edge.png", dpi=150, bbox_inches="tight")
