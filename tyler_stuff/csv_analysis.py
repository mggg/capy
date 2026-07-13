# used to make graphs of the .csv data, analyze it, etc.
# Tyler Piazza, 2/13/19

import numpy as np
import networkx as nx
import json
import csv
import matplotlib.pyplot as plt

from capy import single_brackets, skew, edge, skew_prime, half_edge, half_edge_infinity, morans_I, dissimilarity, gini, true_half_edge_infinity

# be sure to change filename as needed
file = open('POC_W_capy_scores_2000.csv')
csv_from_file = csv.reader(file)

# skip the first line

info_indices = []
edge_index = 4
half_edge_index = 6
half_edge_infinity_index = 8
typo_index = 10
dissim_index = 12
gini_index = 14
moran_index = 16
pop_index = 1
white_rho_index = 3
black_rho_index = 2

info_indices = [edge_index, half_edge_index, half_edge_infinity_index, typo_index, dissim_index, gini_index, moran_index, pop_index, white_rho_index, black_rho_index]

info_dict = {}

name_dict = {}
name_dict[edge_index] = "Edge"
name_dict[half_edge_index] = "Half Edge"
name_dict[half_edge_infinity_index] = "Half Edge Infinity"
name_dict[typo_index] = "Typo (previously Half Edge Infinity)"
name_dict[dissim_index] = "Dissimilarity"
name_dict[gini_index] = "Gini"
name_dict[moran_index] = "Moran's I"
name_dict[pop_index] = "Population"
name_dict[white_rho_index] = "Percentage White"
name_dict[black_rho_index] = "Percentage Black"



for index in info_indices:
  # will append to these lists
  info_dict[index] = []


# Ignoring rank for now, bc the numbers bear that information anyway

for i, row in enumerate(csv_from_file):
  # skip the first lines

  if i < 2:
    # skip over dead line and title lines
    continue
  for index in info_indices:
    info_dict[index].append(float(row[index]))

for index in info_indices:
  val_array = np.array(info_dict[index])
  plt.hist(val_array, bins='auto')
  plt.title(name_dict[index] + " of 2000 cities")
  plt.xlabel(name_dict[index])
  plt.ylabel("Count of U.S. cities")
  plt.savefig("plots_2000/" + name_dict[index] + "_2000.png")
  plt.show()

