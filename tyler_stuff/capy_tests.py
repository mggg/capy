# tests for the capy file, so we know that each function is performing as expected
# Tyler Piazza, 12/6
import numpy as np
import networkx as nx
import json
import csv
import matplotlib.pyplot as plt
import random

from capy import single_brackets, skew, edge, skew_prime, half_edge, half_edge_infinity, true_half_edge_infinity, morans_I, dissimilarity, gini, more_edge, more_half_edge, standard_dev_of_pop, network_statistics, weighted_single_brackets, weighted_half_edge, weighted_edge, true_edge_infinity, remove_dummy_tracts

# this is what we range the scalar values of x and y (if you increase the range, the time for the tests to run goes up)
test_range = range(1,3)

# note that adjacency matrices should be symmetric, and diagonals are 0
x1 = np.array([2, 3])
y1 = np.array([5, 8])
A1 = np.array([[0,1], [1, 0]])

# a -- b

e1 = (2 * 5 + 3 * 8) + 2 * 8 + 3 * 5

x2 = np.array([1, 6, 2])
y2 = np.array([5, 3, 8])
A2 = np.array([[0,1,0],[1,0,1],[0,1,0]])

# a -- b -- c

e2 = (1 * 5 + 6 * 3 + 2 * 8) + (1 * 3 + 5 * 6) + (6 * 8 + 3 * 2)
e2_ = (1 * 1 + 6 * 6 + 2 * 2) + (1 * 6 + 6 * 1) + (2 * 6 + 6 * 2)

# testing some specific cases
assert (single_brackets(x1, y1, A1) == e1)
assert (single_brackets(x2, y2, A2) == e2)
assert (skew(x2, y2, A2) == float(e2_) / float(e2_ + 2 * e2))


deg_dict_1 = network_statistics(A1)
assert(deg_dict_1["mean"] == 1)
assert(deg_dict_1["std_dev"] == 0)
assert(deg_dict_1["max"] == 1)
assert(deg_dict_1["min"] == 1)

deg_dict_2 = network_statistics(A2)
np.testing.assert_approx_equal(deg_dict_2["mean"], (4. / 3.), significant=3)
np.testing.assert_approx_equal(deg_dict_2["std_dev"], 0.47140452079103, significant=3)
assert(deg_dict_2["max"] == 2)
assert(deg_dict_2["min"] == 1)


# for standard deviation
test_pop = np.array([600., 470., 170., 430. , 300.])
assert(int(standard_dev_of_pop(test_pop)) == 147)


# for the dummy tract stuff

def check_tract_assertions(results, my_A, my_list):
  guess_A, guess_list = results
  M = len(my_A)
  for i in range(M):
    for j in range(M):
      assert(guess_A[i,j] == my_A[i,j])

  assert(guess_list == my_list)

# a(real) -- b(real, smaller) - c (dummy)
A = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]])
pop_vec = np.array([10, 5, 0])

check_tract_assertions(remove_dummy_tracts(A, pop_vec), np.array([[0, 1], [1, 0]]), [2])

# a(bigger) -- b(dummy) - c (smaller)
A = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]])
pop_vec = np.array([10, 0, 5])

check_tract_assertions(remove_dummy_tracts(A, pop_vec), np.array([[0, 1], [1, 0]]), [1])


# d is connected to a,b,c. d has zero pop, a has 100, b and c each have 60.
A = np.array([[0, 0, 0, 1], [0, 0, 0, 1], [0, 0, 0, 1], [1, 1, 1, 0]])
pop_vec = np.array([100, 60, 60, 0])


check_tract_assertions(remove_dummy_tracts(A, pop_vec), np.array([[0, 1, 1], [1, 0, 0], [1, 0, 0]]), [3])

# a - b - c - d, b and c are dummy, a has pop 100, d has pop 60

A = np.array([[0, 1, 0, 0], [1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0]])
pop_vec = np.array([100, 0, 0, 60])

check_tract_assertions(remove_dummy_tracts(A, pop_vec), np.array([[0, 1], [1, 0]]), [1,2])

# now, a is connected to all, but c and d are dummies, a has pop 1, b has pop 10

A = np.array([[0, 1, 1, 1], [1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]])
pop_vec = np.array([1, 10, 0, 0])

check_tract_assertions(remove_dummy_tracts(A, pop_vec), np.array([[0, 1], [1, 0]]), [2,3])

# a - b - c - d, where b and d are dummy, and a has the bigger pop

A = np.array([[0, 1, 0, 0], [1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0]])
pop_vec = np.array([91, 0, 35, 0])

check_tract_assertions(remove_dummy_tracts(A, pop_vec), np.array([[0, 1], [1, 0]]), [1,3])




# 2D test cases
# iterate through what the x and y values could be, and iterate through if the two regions are adjacent
for x0 in test_range:
  for x1 in test_range:
    for y0 in test_range:
      for y1 in test_range:
        for c in range(2):
          # c is whether they are adjacent
          x = np.array([x0, x1])
          y = np.array([y0, y1])
          A = np.array([[0,c], [c, 0]])

          # deal with population values
          p0 = x0 + y0
          p1 = x1 + y1

          p = np.array([p0, p1])

          total_pop = p0 + p1
          total_x = x0 + x1

          # e is what the single brackets should be <x,y>
          e = x0 * y0 + x1 * y1 + c * (x0 * y1 + x1 * y0)
          e_weighted_half = (1. / 2.) * (x0 * y0 + x1 * y1) + c * (x0 * y1 + x1 * y0)
          e_weighted_third = (1. / 3.) * (x0 * y0 + x1 * y1) + c * (x0 * y1 + x1 * y0)
          e_xx_third = (1. / 3.) * (x0 * x0 + x1 * x1) + c * (x0 * x1 + x1 * x0)
          e_yy_third = (1. / 3.) * (y0 * y0 + y1 * y1) + c * (y0 * y1 + y1 * y0)

          weighted_half_edge_third = (1./2.) * ((e_xx_third / (e_xx_third + e_weighted_third)) + (e_yy_third / (e_yy_third + e_weighted_third)))
          weighted_edge_third = (1. / 2.) * ((e_xx_third / (e_xx_third + 2. * e_weighted_third)) + (e_yy_third / (e_yy_third + 2. * e_weighted_third)))

          e_x = x0 * x0 + x1 * x1 + c * (x0 * x1 + x1 * x0)
          e_y = y0 * y0 + y1 * y1 + c * (y0 * y1 + y1 * y0)

          # for testing skew, with x or y in front
          skew_x = (float(e_x) / (e_x + 2 * e))
          skew_y = (float(e_y) / (e_y + 2 * e))

          skew_prime_x = (float(e_x) / (e_x + e))
          skew_prime_y = (float(e_y) / (e_y + e))

          # for testing half-edge infinity
          x_square_sum = float(x0 * x0 + x1 * x1)
          y_square_sum = float(y0 * y0 + y1 * y1)
          x_denom = float(x0 + x0 * x0 * y0 + x1 + x1 * x1 * y1)
          y_denom = float(y0 + y0 * x0 * y0 + y1 + y1 * x1 * y1)
          # then for the true half edge infinity
          true_x_denom = float(x0 * x0 + x0 * y0 + x1 * x1 + x1 * y1)
          true_y_denom = float(y0 * y0 + x0 * y0 + y1 * y1 + x1 * y1)

          edge_inf_x_denom = float(x0 * x0 + 2. * x0 * y0 + x1 * x1 + 2. * x1 * y1)
          edge_inf_y_denom = float(y0 * y0 + 2. * x0 * y0 + y1 * y1 + 2. * x1 * y1)

          # for testing moran's I
          n = 2.
          x_avg = float(x0 + x1) / n
          moran_num = float(n * 2 * (x0 - x_avg) * (x1 - x_avg))
          moran_denom = float(2 * c * ((x0 - x_avg) ** 2 + (x1 - x_avg) ** 2))

          # for testing dissimilarity and gini
          pop_denom = float(2 * total_x * (total_pop - total_x))
          dissim_sum = float(abs(x0 * total_pop - p0 * total_x) + abs(x1 * total_pop - p1 * total_x))
          gini_sum = float(abs(x0 * p1 - p0 * x1) +  abs(x1 * p0 - p1 * x0))

          assert (single_brackets(x, y, A) == e)
          assert (weighted_single_brackets(x, y, 0.5, A) == e_weighted_half)
          #assert (weighted_single_brackets(x, y, (1./3.), A) == e_weighted_third)
          np.testing.assert_approx_equal(weighted_single_brackets(x, y, (1./3.), A), e_weighted_third, significant=10)
          np.testing.assert_approx_equal(weighted_half_edge(x, y, (1./3.), A), weighted_half_edge_third, significant=10)
          np.testing.assert_approx_equal(weighted_edge(x, y, (1./3.), A), weighted_edge_third, significant=10)
          assert (skew(x, y, A) == skew_x)
          assert (edge(x, y, A) == (0.5) * (skew_x + skew_y))
          assert (skew_prime(x, y, A) == skew_prime_x)
          assert (half_edge(x, y, A) == (0.5) * (skew_prime_x + skew_prime_y))
          assert (half_edge_infinity(x, y, A) == (0.5) * (x_square_sum / x_denom + y_square_sum / y_denom))
          assert (true_half_edge_infinity(x, y, A) == (0.5) * (x_square_sum / true_x_denom + y_square_sum / true_y_denom))
          assert (true_edge_infinity(x, y, A) == (0.5) * (x_square_sum / edge_inf_x_denom + y_square_sum / edge_inf_y_denom))
          if (c > 0) and not (x_avg == x0):
            assert (morans_I(x, A) == moran_num / moran_denom)
          assert(dissimilarity(x, p) == dissim_sum / pop_denom)
          assert(gini(x, p) == gini_sum / pop_denom)


print "onto the 3 block cases"

# 3 block test cases, similarly loop through what x and y could be, and loop through possible adjacencies
for x0 in test_range:
  for x1 in test_range:
    for x2 in test_range:
      for y0 in test_range:
        for y1 in test_range:
          for y2 in test_range:
            for z0 in test_range:
              for z1 in test_range:
                for z2 in test_range:
                  for adj_01 in range(2):
                    for adj_02 in range(2):
                      for adj_12 in range(2):

                        x = np.array([x0, x1, x2])
                        y = np.array([y0, y1, y2])
                        z = np.array([z0, z1, z2])

                        A = np.array([[0, adj_01, adj_02], [adj_01, 0, adj_12], [adj_02, adj_12, 0]])

                        p0 = x0 + y0
                        p1 = x1 + y1
                        p2 = x2 + y2

                        p = np.array([p0, p1, p2])

                        total_pop = p0 + p1 + p2
                        total_x = x0 + x1 + x2




                        # this set of for-loops also goes through more_edge and more_half_edge, so we need these extra values
                        e_xy = float(x0 * y0 + x1 * y1 + x2 * y2 + adj_01 * (x0 * y1 + x1 * y0) + adj_02 * (x0 * y2 + x2 * y0) + adj_12 * (x1 * y2 + x2 * y1))
                        e_xz = float(x0 * z0 + x1 * z1 + x2 * z2 + adj_01 * (x0 * z1 + x1 * z0) + adj_02 * (x0 * z2 + x2 * z0) + adj_12 * (x1 * z2 + x2 * z1))
                        e_zy = float(z0 * y0 + z1 * y1 + z2 * y2 + adj_01 * (z0 * y1 + z1 * y0) + adj_02 * (z0 * y2 + z2 * y0) + adj_12 * (z1 * y2 + z2 * y1))

                        e_x = float(x0 * x0 + x1 * x1 + x2 * x2 + adj_01 * (x0 * x1 + x1 * x0) + adj_02 * (x0 * x2 + x2 * x0) + adj_12 * (x1 * x2 + x2 * x1))
                        e_y = float(y0 * y0 + y1 * y1 + y2 * y2 + adj_01 * (y0 * y1 + y1 * y0) + adj_02 * (y0 * y2 + y2 * y0) + adj_12 * (y1 * y2 + y2 * y1))
                        e_z = float(z0 * z0 + z1 * z1 + z2 * z2 + adj_01 * (z0 * z1 + z1 * z0) + adj_02 * (z0 * z2 + z2 * z0) + adj_12 * (z1 * z2 + z2 * z1))

                        # for the weighted version
                        e_xy_weighted_half = float((0.5) * (x0 * y0 + x1 * y1 + x2 * y2 )+ adj_01 * (x0 * y1 + x1 * y0) + adj_02 * (x0 * y2 + x2 * y0) + adj_12 * (x1 * y2 + x2 * y1))


                        skew_x = (float(e_x) / (e_x + 2 * e_xy))
                        skew_y = (float(e_y) / (e_y + 2 * e_xy))

                        skew_prime_x = (float(e_x) / (e_x + e_xy))
                        skew_prime_y = (float(e_y) / (e_y + e_xy))

                        # for dealing with z
                        more_edge_test = 1. / 3. * (e_x / (e_x + 2. * (e_xy + e_xz)) +  e_y / (e_y + 2. * (e_xy + e_zy)) + e_z / (e_z + 2. * (e_xz + e_zy)))
                        more_half_edge_test = 1. / 3. * (e_x / (e_x +  (e_xy + e_xz)) +  e_y / (e_y + (e_xy + e_zy)) + e_z / (e_z + (e_xz + e_zy)))


                        x_square_sum = float(x0 * x0 + x1 * x1 + x2 * x2)
                        y_square_sum = float(y0 * y0 + y1 * y1 + y2 * y2)
                        x_denom = float(x0 + x0 * x0 * y0 + x1 + x1 * x1 * y1 + x2 + x2 * x2 * y2)
                        y_denom = float(y0 + y0 * x0 * y0 + y1 + y1 * x1 * y1 + y2 + y2 * x2 * y2)
                        # for the true half edge infinity
                        true_x_denom = float(x0 * x0 + x0 * y0 + x1 * x1 + x1 * y1 + x2 * x2 + x2 * y2)
                        true_y_denom = float(y0 * y0 + x0 * y0 + y1 * y1 + x1 * y1 + y2 * y2 + x2 * y2)



                        n = 3.
                        x_avg = float(x0 + x1 + x2) / n
                        moran_num = float(2 * n * (adj_01 * (x0 - x_avg) * (x1 - x_avg) + adj_02 * (x0 - x_avg) * (x2 - x_avg) + adj_12 * (x1 - x_avg) * (x2 - x_avg)))
                        moran_denom = float((2 * (adj_01 + adj_02 + adj_12)) * ((x0 - x_avg) ** 2 + (x1 - x_avg) ** 2 + (x2 - x_avg) ** 2 ))

                        # for gini and dissimilarity
                        pop_denom = float(2 * total_x * (total_pop - total_x))
                        dissim_sum = float(abs(x0 * total_pop - p0 * total_x) + abs(x1 * total_pop - p1 * total_x) + abs(x2 * total_pop - p2 * total_x))
                        gini_sum = 2. * float(abs(x0 * p1 - p0 * x1) +  abs(x0 * p2 - p0 * x2) + abs(x1 * p2 - p1 * x2))

                        assert (single_brackets(x, y, A) == e_xy)
                        assert (weighted_single_brackets(x, y, 0.5, A) == e_xy_weighted_half)
                        assert (skew(x, y, A) == skew_x)
                        assert (edge(x, y, A) == (0.5) * (skew_x + skew_y))
                        assert (more_edge([x, y], A) == (0.5) * (skew_x + skew_y))
                        np.testing.assert_approx_equal(more_edge([x, y, z], A), more_edge_test, significant=10)

                        assert (skew_prime(x, y, A) == skew_prime_x)
                        assert (half_edge(x, y, A) == (0.5) * (skew_prime_x + skew_prime_y))
                        assert (more_half_edge([x, y], A) == (0.5) * (skew_prime_x + skew_prime_y))
                        np.testing.assert_approx_equal(more_half_edge([x, y, z], A), more_half_edge_test, significant=10)

                        assert (half_edge_infinity(x, y, A) == (0.5) * (x_square_sum / x_denom + y_square_sum / y_denom))
                        assert (true_half_edge_infinity(x, y, A) == (0.5) * (x_square_sum / true_x_denom + y_square_sum / true_y_denom))
                        if (moran_denom > 0):
                          np.testing.assert_approx_equal(morans_I(x, A), (moran_num / moran_denom), significant=10)
                        np.testing.assert_approx_equal(dissimilarity(x, p), dissim_sum / pop_denom, significant=10)
                        np.testing.assert_approx_equal(gini(x, p), gini_sum / pop_denom, significant=10)

print "onto the 4 block test cases"

# 4D test cases
# again, loop through possible adjacencies
for x0 in test_range:
  for x1 in test_range:
    for x2 in test_range:
      for x3 in test_range:
        for y0 in test_range:
          for y1 in test_range:
            for y2 in test_range:
              for y3 in test_range:
                for adj_01 in range(2):
                  for adj_02 in range(2):
                    for adj_03 in range(2):
                      for adj_12 in range(2):
                        for adj_13 in range(2):
                          for adj_23 in range(2):

                            x = np.array([x0, x1, x2, x3])
                            y = np.array([y0, y1, y2, y3])
                            A = np.array([[0, adj_01, adj_02, adj_03], [adj_01, 0, adj_12, adj_13], [adj_02, adj_12, 0, adj_23], [adj_03, adj_13, adj_23, 0]])

                            p0 = x0 + y0
                            p1 = x1 + y1
                            p2 = x2 + y2
                            p3 = x3 + y3

                            p = np.array([p0, p1, p2, p3])

                            total_pop = p0 + p1 + p2 + p3
                            total_x = x0 + x1 + x2 + x3

                            e = (x0 * y0 + x1 * y1 + x2 * y2 + x3 * y3) + adj_01 * (x0 * y1 + x1 * y0) + adj_02 * (x0 * y2 + x2 * y0) + adj_03 * (x0 * y3 + x3 * y0) + adj_12 * (x1 * y2 + x2 * y1) + adj_13 * (x1 * y3 + x3 * y1) + adj_23 * (x3 * y2 + x2 * y3)
                            e_x = (x0 * x0 + x1 * x1 + x2 * x2 + x3 * x3) + adj_01 * (x0 * x1 + x1 * x0) + adj_02 * (x0 * x2 + x2 * x0) + adj_03 * (x0 * x3 + x3 * x0) + adj_12 * (x1 * x2 + x2 * x1) + adj_13 * (x1 * x3 + x3 * x1) + adj_23 * (x3 * x2 + x2 * x3)
                            e_y = (y0 * y0 + y1 * y1 + y2 * y2 + y3 * y3) + adj_01 * (y0 * y1 + y1 * y0) + adj_02 * (y0 * y2 + y2 * y0) + adj_03 * (y0 * y3 + y3 * y0) + adj_12 * (y1 * y2 + y2 * y1) + adj_13 * (y1 * y3 + y3 * y1) + adj_23 * (y3 * y2 + y2 * y3)

                            skew_x = (float(e_x) / (e_x + 2 * e))
                            skew_y = (float(e_y) / (e_y + 2 * e))

                            skew_prime_x = (float(e_x) / (e_x + e))
                            skew_prime_y = (float(e_y) / (e_y + e))

                            x_square_sum = float(x0 * x0 + x1 * x1 + x2 * x2 + x3 * x3)
                            y_square_sum = float(y0 * y0 + y1 * y1 + y2 * y2 + y3 * y3)
                            x_denom = float(x0 + x0 * x0 * y0 + x1 + x1 * x1 * y1 + x2 + x2 * x2 * y2 + x3 + x3 * x3 * y3)
                            y_denom = float(y0 + y0 * x0 * y0 + y1 + y1 * x1 * y1 + y2 + y2 * x2 * y2 + y3 + y3 * x3 * y3)
                            # for the true half edge infinity
                            true_x_denom = float(x0 * x0 + x0 * y0 + x1 * x1 + x1 * y1 + x2 * x2 + x2 * y2 + x3 * x3 + x3 * y3)
                            true_y_denom = float(y0 * y0 + x0 * y0 + y1 * y1 + x1 * y1 + y2 * y2 + x2 * y2 + y3 * y3 + x3 * y3)


                            n = 4.
                            x_avg = float(x0 + x1 + x2 + x3) / n
                            moran_num = float(2 * n * (adj_01 * (x0 - x_avg) * (x1 - x_avg) + adj_02 * (x0 - x_avg) * (x2 - x_avg) + adj_03 * (x0 - x_avg) * (x3 - x_avg) + adj_12 * (x1 - x_avg) * (x2 - x_avg) + adj_13 * (x1 - x_avg) * (x3 - x_avg) + adj_23 * (x2 - x_avg) * (x3 - x_avg)))
                            moran_denom = float((2 * (adj_01 + adj_02 + adj_03 + adj_12 + adj_13 + adj_23)) * ((x0 - x_avg) ** 2 + (x1 - x_avg) ** 2 + (x2 - x_avg) ** 2 + (x3 - x_avg) ** 2))


                            # for gini and dissimilarity
                            pop_denom = float(2 * total_x * (total_pop - total_x))
                            dissim_sum = float(abs(x0 * total_pop - p0 * total_x) + abs(x1 * total_pop - p1 * total_x) + abs(x2 * total_pop - p2 * total_x) + abs(x3 * total_pop - p3 * total_x))
                            gini_sum = 2. * float(abs(x0 * p1 - p0 * x1) +  abs(x0 * p2 - p0 * x2) + abs(x0 * p3 - p0 * x3) + abs(x1 * p2 - p1 * x2) + abs(x1 * p3 - p1 * x3) + abs(x2 * p3 - p2 * x3) )

                            assert (single_brackets(x, y, A) == e)
                            assert (skew(x, y, A) == skew_x)
                            assert (edge(x, y, A) == (0.5) * (skew_x + skew_y))
                            assert (skew_prime(x, y, A) == skew_prime_x)
                            assert (half_edge(x, y, A) == (0.5) * (skew_prime_x + skew_prime_y))
                            assert (half_edge_infinity(x, y, A) == (0.5) * (x_square_sum / x_denom + y_square_sum / y_denom))
                            assert (true_half_edge_infinity(x, y, A) == (0.5) * (x_square_sum / true_x_denom + y_square_sum / true_y_denom))

                            if (moran_denom > 0):
                              np.testing.assert_approx_equal(morans_I(x, A),(moran_num / moran_denom), significant=10)
                            np.testing.assert_approx_equal(dissimilarity(x, p),dissim_sum / pop_denom, significant=10)
                            np.testing.assert_approx_equal(gini(x, p), gini_sum / pop_denom, significant=10)

