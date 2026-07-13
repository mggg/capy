# to compute various demographic scores
# Tyler, 5/6/19

import numpy as np
import networkx as nx
import json
import csv
import matplotlib.pyplot as plt
from sets import Set

# <x,y> =  x^T(A+I)y = sum_i x_iy_i + sum_{i \sim j}x_iy_i + x_jy_i
def single_brackets(x, y, A):
    return np.matmul(x.T, np.matmul((A + np.identity(A[0].size)), y))

# THE WEIGHTED VERSION
# <x,y>_lambda = lambda(sum_i x_iy_i) + sum_{i \sim j}x_iy_i + x_jy_i
# this is equivalent to scaling the identity matrix from above by lambda
def weighted_single_brackets(x, y, lam, A):
    return np.matmul(x.T, np.matmul((A + lam * np.identity(A[0].size)), y))


# <x,x> / (<x,x> + 2<x,y>)
# not suitably designed for more than 2 values yet
def skew(x, y, A):
  x_prod = single_brackets(x, x, A)
  return float(x_prod) / float(x_prod + 2 * single_brackets(x, y, A))

def edge(x, y, A):
  # JUST defined for 2 for now. See more_edge for more than 2
  skew_sum = 0
  for (a,b) in [(x,y), (y, x)]:
    skew_sum += skew(a, b, A)

  edge_result = float(skew_sum) / float(2)
  return edge_result


# more_edge is edge, handling more than 2 demographics
# dem_list is a list of vectors like x,y from previous functions
def more_edge(dem_list, A):
  n = len(dem_list)
  # first up, compute the single brackets (i,j) for all i,j in [n] x [n]
  single_bracket_matrix = [[0 for i in range(n)] for j in range(n)]
  for i in range(n):
    for j in range(i,n):
      single_bracket_matrix[i][j] = single_brackets(dem_list[i], dem_list[j], A)
      # for ease of calling the values later,
      single_bracket_matrix[j][i] = single_bracket_matrix[i][j]

  skew_sum = 0.
  for i in range(n):
    skew_denom = 0.
    for j in range(n):
      skew_denom += single_bracket_matrix[i][j]
    skew_denom *= 2.
    skew_denom -= single_bracket_matrix[i][i]
    skew_term = float((single_bracket_matrix[i][i])) / float(skew_denom)

    skew_sum += skew_term

  skew_sum /= float(n)
  # then scale by 1/n
  return skew_sum

# weighted variant of edge - equivalent definition, but with weighted variant of single brackets
def weighted_edge(x, y, lam, A):
  wsb_xx = float(weighted_single_brackets(x,x,lam,A))
  wsb_yy = float(weighted_single_brackets(y,y,lam,A))
  wsb_xy = float(weighted_single_brackets(x,y,lam,A))
  holder = float(wsb_xx) / float(wsb_xx + 2. * wsb_xy)
  holder += float(wsb_yy) / float(wsb_yy + 2. * wsb_xy)
  holder *= 0.5
  return holder


# equivalent definition as in half edge, except for the extra factor of 2 in a term in the denominators
# ex. the first denominator should be sum x_i^2 + 2sum x_iy_i
def true_edge_infinity(x, y, A):
  x_square_sum = 0
  y_square_sum = 0
  first_denom = 0
  second_denom = 0
  n = len(x)
  for i in range(n):
    a = x[i]
    b = y[i]
    x_square_sum += a * a
    y_square_sum += b * b
    first_denom += a * a + 2. * a * b
    second_denom += b * b + 2. * a * b

  term1 = float(x_square_sum) / float(first_denom)
  term2 = float(y_square_sum) / float(second_denom)
  result = (term1 + term2) / 2.
  return result

#<x,x> / (<x,x> + <x,y>)
def skew_prime(x, y, A):
  x_prod = single_brackets(x, x, A)
  return float(x_prod) / float(x_prod + single_brackets(x, y, A))

# note: not made for more than 2 yet
# average the skew primes
def half_edge(x, y, A):
  skew_sum = 0
  for (a,b) in [(x,y), (y, x)]:
    skew_sum += skew_prime(a, b, A)
  edge_result = float(skew_sum) / float(2)
  return edge_result

# more_half_edge is half_edge, handling more than 2 demographics
# dem_list is a list of vectors like x,y from previous functions
def more_half_edge(dem_list, A):
  n = len(dem_list)
  # first up, compute the single brackets (i,j) for all i,j in [n] x [n]
  single_bracket_matrix = [[0 for i in range(n)] for j in range(n)]
  for i in range(n):
    for j in range(i,n):
      single_bracket_matrix[i][j] = single_brackets(dem_list[i], dem_list[j], A)
      # for ease of calling the values later,
      single_bracket_matrix[j][i] = single_bracket_matrix[i][j]

  skew_p_sum = 0.
  for i in range(n):
    skew_p_denom = 0.
    for j in range(n):
      skew_p_denom += single_bracket_matrix[i][j]
    skew_p_term = float((single_bracket_matrix[i][i])) / float(skew_p_denom)

    skew_p_sum += skew_p_term

  skew_p_sum /= float(n)
  return skew_p_sum

# the weighted version of half edge TBD
def weighted_half_edge(x, y, lam, A):
  wsb_xx = float(weighted_single_brackets(x,x,lam,A))
  wsb_yy = float(weighted_single_brackets(y,y,lam,A))
  wsb_xy = float(weighted_single_brackets(x,y,lam,A))
  holder = float(wsb_xx) / float(wsb_xx + wsb_xy)
  holder += float(wsb_yy) / float(wsb_yy + wsb_xy)
  holder *= 0.5
  return holder


""" NOTE: this is referred to as "typo" in our literature. It is the incorrect
formula for what is half edge. However, this "typo" ends up explaining the difference
between edge and half edge
"""
def half_edge_infinity(x, y, A):
  # see note above about how this is NOT the true value of half edge infinity
  x_square_sum = 0
  y_square_sum = 0
  first_denom = 0
  second_denom = 0
  n = len(x)
  for i in range(n):
    a = x[i]
    b = y[i]
    x_square_sum += a * a
    y_square_sum += b * b
    first_denom += a + a * a * b
    second_denom += b + b * a * b

  term1 = float(x_square_sum) / float(first_denom)
  term2 = float(y_square_sum) / float(second_denom)
  result = (term1 + term2) / 2.
  return result

"""  NOTE: this is the true "half edge infinity" (i.e. it is the limit of half
edge as the weights in weighted single brackets go to infinity)

"""
def true_half_edge_infinity(x, y, A):
  x_square_sum = 0
  y_square_sum = 0
  first_denom = 0
  second_denom = 0
  n = len(x)
  for i in range(n):
    a = x[i]
    b = y[i]
    x_square_sum += a * a
    y_square_sum += b * b
    # the only difference between this half edge infinity and the "typo"
    # are the following two lines of code. Notice that a + becomes a * and vice
    #versa  so the first_denom should be sum x_i^2 + sum x_iy_i
    first_denom += a * a + a * b
    second_denom += b * b + a * b

  term1 = float(x_square_sum) / float(first_denom)
  term2 = float(y_square_sum) / float(second_denom)
  result = (term1 + term2) / 2.
  return result

# just runs over pairs i,j such that i<j, and sums the matrix, then multiplies by 2
def smart_symmetric_matrix_sum(A):
  n = len(A)
  accumulator = 0
  for i in range(n):
    for j in range(i + 1, n):
      accumulator += A[i,j]

  return float(2 * accumulator)

# moran's I
# n/(|E|) * (v^TAv)/(v^Tv)
# where v is x, minus a vector with just mean
def morans_I(x, A):
  n = float(len(x))
  E = smart_symmetric_matrix_sum(A)
  v = x - np.average(x)
  # (v^TAv)
  r_num = float(np.matmul(v.T, np.matmul((A), v)))
  # (v^Tv)
  r_denom = float(np.matmul(v.T,  v))
  r_quotient = r_num / r_denom
  return (n / E) * r_quotient

# total pop vector is a vector of the TOTAL population of each region, with same indices as x
def dissimilarity(x, total_pop_vector):
  total_pop = np.sum(total_pop_vector)
  x_pop = np.sum(x)
  n = len(x)
  first_term = 1. / float(2 * x_pop * (total_pop - x_pop))
  accumulator = 0.
  for i in range(n):
    accumulator += abs(x[i] * total_pop - total_pop_vector[i] * x_pop)
  return first_term * accumulator

# total_pop_vector similarly defined as before
def gini(x, total_pop_vector):
  total_pop = np.sum(total_pop_vector)
  x_pop = np.sum(x)
  n = len(x)
  first_term = 1. / float(2 * x_pop * (total_pop - x_pop))
  accumulator = 0.
  for i in range(n):
    for j in range(i + 1, n):
      accumulator += abs(x[i] * total_pop_vector[j] - total_pop_vector[i] * x[j])
  # the factor of 2 is necessary because we technically sum over all n^2 pairs (i,j), but I only did distinct pairs, and we ignore i=j
  return first_term * accumulator * 2

# compute evenness of population across tracts/units
def standard_dev_of_pop(total_pop_vector):
  return np.std(total_pop_vector)

def network_statistics(A):
  # first, get a vector that is the sum of the rows of A
  n = len(A)
  degrees = []
  for i in range(n):
    degree_counter = 0
    for j in range(n):
      degree_counter += A[i,j]
    degrees.append(degree_counter)
  degree_val_dict = {}
  degree_val_dict["max"] = max(degrees)
  degree_val_dict["min"] = min(degrees)

  degrees = np.array(degrees)
  degree_val_dict["mean"] = np.mean(degrees)
  degree_val_dict["std_dev"] = np.std(degrees)


  return degree_val_dict


""" this function is meant to handle the "dummy tract" problem, where shapefiles
have tracts with zero population
Our solution is to remove them from the adjacency matrix, but effectively "merge"
them into the nearest tract with the largest population
"""

# I assume that dummy tracts are either completely isolated, or adjacent to a non-dummy tract
def remove_dummy_tracts(A, pop_vec):
  # returns a new A, as well as a list of entries to remove
  dummy_set = Set()
  N = len(pop_vec)
  for i in range(N):
    if pop_vec[i] == 0:
      dummy_set.add(i)

  # what happens if a node has nowhere to go? Well, just wipe it off the face of the earth
  for i in dummy_set:
    tracts_reachable_from_dummy = []
    for j in range(N):
      if A[i,j] == 1:
        tracts_reachable_from_dummy.append(j)

    # now, find those with
    max_pop = -1
    best_tract = -1
    for j in tracts_reachable_from_dummy:
      if pop_vec[j] > max_pop:
        max_pop = max(pop_vec[j], max_pop)
        best_tract = j
    # i.e. if it is not an island
    if best_tract > -1:
      for j in tracts_reachable_from_dummy:
        if j != best_tract:
          A[best_tract, j] = 1
          A[j, best_tract] = 1

  # then, we must go through and create a new numpy matrix
  new_N = N - len(dummy_set)
  new_A = np.array([[0. for b in range(new_N)] for a in range(new_N)])
  i_placement = 0
  j_placement = 0
  for i in range(N):
    if i not in dummy_set:
      j_placement = 0
      for j in range(N):
        if j not in dummy_set:
          # creating the new adjacency matrix
          new_A[i_placement, j_placement] = A[i, j]
          j_placement += 1
      i_placement += 1

  # return the new adjacency matrix, as well as the set of dummy vertices, so you can remove them from your other vectors
  print "throwing out " + str(len(dummy_set)) + " dummy nodes"
  return new_A, list(dummy_set)
