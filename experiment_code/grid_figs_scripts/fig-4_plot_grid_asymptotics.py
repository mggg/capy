import sys, os
import matplotlib.pyplot as plt
import numpy as np

###This script replicates the top right half of figure 4. in the preprint https://mggg.org/Capy.pdf. It makes lineplots of capy score
####versus rho of on ideal confiogurations of asymptotically large grids. 

def half_edge_a_ch(rho)->float:
    """
    Generates capy value of a checkerboard configuration on an n by n grid as n goes to infinity. Checkerboard configurations
    are defined as when half the nodes are all x the other half are all y and neither x or y nodes have neighbours of the same type
    Args: rho (float), the grid's minority proportion
    Returns: the half edge value of the grid for that value of rho
    """
    return (5 - 8 * rho) / (2 * (5 - 5 * rho))

def half_edge_a_isol(rho)->float:
    """
    Generates capy value of an isolated configuration on an n by n grid as n goes to infinity. Isolated configurations
    are defined as when each node is either all x or all y and x nodes have no x neighbours
    Args: rho (float), the grid's minority proportion
    Returns: the half edge value of the grid for that value of rho
    """

    return (3 - 5 * rho) / (5 - 5 * rho)

def half_edge_a_const(rho:float)->float:
    """
    Returns the capy value of an nxn grid where each node contains rho*M members of group x and (1-rh)*M group y, 
    where M is the node's total population as n goes to infinity.
        Args: rho, the grid's minority proportion
        Returns: the half edge value of the grid for that value of rho
    """
    return .5

def half_edge_a_one_clust(rho:float)->float:
    """
    Returns the capy value of an nxn grid where each node is either all x or all y and x nodes are distributed 
    in a square with side length n $\sqrt(\rho) * n$ as n goes to infinity.
        Args: rho, the grid's minority proportion
        Returns: the half edge value of the grid for that value of rho
    """
    return 1

#plotting the image
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

plt.plot(x, isol, label="Isolated", color = "#69359c")
plt.plot(x, ch, label="Checkerboard", color =  "#1560bd")
plt.plot(x, const, label="Constant", color = "#ffa812")
plt.plot(x, one_clust, label="One Cluster", color = "#006B3C")

plt.legend(fontsize=8, handlelength=1.5, handleheight=.75, handletextpad=0.4, borderpad=0.4)

plt.xlabel("Minority Proportion")
plt.ylabel("Capy")
plt.savefig("Reproduction/Reproduction_Figures/Idealized_Grids/fig-4_grid_asymptotics_half_edge.png", dpi=150, bbox_inches="tight")
