# for the MAUP problem
# Tyler Piazza
# 5/1/19
import numpy as np
import networkx as nx
import json
import csv
import matplotlib.pyplot as plt

from capy import single_brackets, skew, edge, skew_prime, half_edge, half_edge_infinity, morans_I, dissimilarity, gini, true_half_edge_infinity, standard_dev_of_pop, network_statistics, remove_dummy_tracts

# removed 'Riverside-San-Bernardino-Ontario_CA' to match with 2000
# removed 'Ithaca_NY' to get 100 cities
chicago_MAUP_cities = ["Chicago_metro_blckgrps", "Chicago_metro_tracts"]
chicago_MAUP_cities_intersection = ["Chicago_metro_blckgrps_intersection", "Chicago_metro_tracts_intersection"]
pop_dict = {}
city_names = sorted(chicago_MAUP_cities_intersection)

b_scores = [[]]
h_scores = [[]]
a_scores = [[]]

b_scores.append(["City", "Number of Units", "Total polulation", "Percent Black", "Percent White", "Edge" , "Edge rank",  "HEdge", "HEdge rank", "HEdgeInfinity (True)", "HEdgeInfinity (True) rank", "Typo HEI", "Typo HEI rank", "Dissimilarity", "Dissimilarity rank",  "Gini", "Gini rank", "Moran's I", "Moran's I rank", "Population standard deviation", "Degree average", "Degree standard deviation", "Max degree", "Min degree"])

bEdge = []
bHEdge = []
bDiss = []
bFrey = []
bAssort = []
bMoran = []

#we compute scores
print "double check this list"
for city in city_names:
#for city in names_of_files_for_pop_histogram:
    print (city)
    with open('MAUP/jsonsMAUP/'+city+'_data.json') as f:
        data = json.load(f)
    #g = nx.adjacency_graph(data)
    g = nx.readwrite.json_graph.adjacency_graph(data)
    g = nx.convert_node_labels_to_integers(g)

    num_vtds = g.number_of_nodes()

    # get demographic and total population vectors
    old_white = np.zeros((num_vtds,1))
    old_black = np.zeros((num_vtds,1))
    old_asian = np.zeros((num_vtds,1))
    old_hisp = np.zeros((num_vtds,1))
    old_amein = np.zeros((num_vtds,1))
    old_natpac = np.zeros((num_vtds,1))
    old_other = np.zeros((num_vtds,1))
    old_tot = np.zeros((num_vtds,1))
    old_nb = np.zeros((num_vtds,1))
    old_nh = np.zeros((num_vtds,1))
    old_na = np.zeros((num_vtds,1))
    # the score that we will be using
    old_poc = np.zeros((num_vtds,1))

    #here we add the demographics we want to compute the scores for. Currently we compute the scores for white - demographic and for demographic and its complementary set.
    dems = [old_black, old_asian, old_hisp]
    comps = [old_nb, old_na, old_nh]

    #nhgis00012: NOT HISPANIC, WHITE ALONE
    #nhgis00013: NOT HISPANIC, BLACK ALONE
    #nhgis00014: NOT HISPANIC, ASIAN ALONE
    #nhgis00015: NOT HISPANIC, NATIVE HAWAIIAN/PACIFIC ISLANDER ALONE
    #nhgis00016: NOT HISPANIC, OTHER RACE ALONE

    # and then the HISPANIC portion
    #nhgis00017: HISPANIC, WHITE
    #nhgis00018: HISPANIC, BLACK
    #nhgis00019: HISPANIC, ASIAN
    #nhgis00020: HISPANIC, NATIVE HAWAIIAN/PACIFIC ISLANDER
    #nhgis00021: HISPANIC, OTHER RACE
    n_tracts = g.number_of_nodes()
    if n_tracts <= 30:
        print "NUMBER OF TRACTS IS LOW: " + str(n_tracts)
        continue

    # assign demographic population per geographic unit
    for i in range(n_tracts):
        # I assume that each category is discrete (there are no people in multiple categories)
        old_white[i] = g.nodes[i]['POP_WHITE']
        old_black[i] = g.nodes[i]['POP_BLACK']
        old_asian[i] = g.nodes[i]['POP_ASIAN']

        # add up the different variants of hispanic
        old_hisp[i] = g.nodes[i]['POP_HISP']

        old_natpac[i] = g.nodes[i]['POP_NHPI']
        old_other[i] = g.nodes[i]['POP_AMIN'] + g.nodes[i]['POP_OTHER'] + g.nodes[i]['POP_2MORE']
        # need to modify
        old_tot[i] = old_white[i] + old_black[i] + old_asian[i] + old_hisp[i] + old_natpac[i] + old_other[i]
        old_nb[i] = old_tot[i] - old_black[i]
        old_nh[i] = old_tot[i] - old_hisp[i]
        old_na[i] = old_tot[i] - old_asian[i]
        old_poc[i] = old_tot[i] - old_white[i]


    # maybe I can use these vectors, sum them up, etc.
    total_white = old_white.sum()
    total_black = old_black.sum()
    total_pop = old_tot.sum()

    white_rho = float(total_white) / float(total_pop) * 100.
    black_rho = float(total_black) / float(total_pop) * 100.

    print "white_rho is " + str(white_rho) + " and black rho is " + str(black_rho)
    # make adjacency matrix
    A = nx.to_numpy_matrix(g)
    # rehandle the matrices...
    A_new, dummy_list = remove_dummy_tracts(A, old_tot)
    A = A_new

    new_n_tracts = n_tracts - len(dummy_list)

    white = np.zeros((new_n_tracts,1))
    black = np.zeros((new_n_tracts,1))
    asian = np.zeros((new_n_tracts,1))
    hisp = np.zeros((new_n_tracts,1))
    amein = np.zeros((new_n_tracts,1))
    natpac = np.zeros((new_n_tracts,1))
    other = np.zeros((new_n_tracts,1))
    tot = np.zeros((new_n_tracts,1))
    nb = np.zeros((new_n_tracts,1))
    nh = np.zeros((new_n_tracts,1))
    na = np.zeros((new_n_tracts,1))
    # the score that we will be using
    poc = np.zeros((new_n_tracts,1))

    new_placement = 0

    for i in range(n_tracts):
        if not i in dummy_list:
            # have to create these new vectors...
            white[new_placement] = old_white[i]
            black[new_placement] = old_black[i]
            asian[new_placement] = old_asian[i]

            # add up the different variants of hispanic
            hisp[new_placement] = old_hisp[i]
            natpac[new_placement] = old_natpac[i]
            other[new_placement] = old_other[i]
            # need to modify
            tot[new_placement] = old_tot[i]
            nb[new_placement] = old_nb[i]
            nh[new_placement] = old_nh[i]
            na[new_placement] = old_na[i]
            poc[new_placement] = old_poc[i]

            new_placement += 1


    n_tracts = new_n_tracts

    #compute and store the energy scores in a csv
    btemplist = []
    # info, like name, population, black rho, and white rho (percentage of that pop in the city)
    btemplist.append(city)
    btemplist.append(n_tracts)
    btemplist.append(total_pop)
    btemplist.append(black_rho)
    btemplist.append(white_rho)

    # now compute interesting scoprs
    btemplist.append(edge(poc, white, A))
    btemplist.append(half_edge(poc, white, A))
    btemplist.append(true_half_edge_infinity(poc, white, A))
    btemplist.append(half_edge_infinity(poc, white, A))
    btemplist.append((dissimilarity(poc, tot))[0])
    btemplist.append((gini(poc, tot))[0])
    btemplist.append(morans_I(poc,A))

    # for adding standard deviation across
    btemplist.append(standard_dev_of_pop(tot))

    # network statistics
    deg_dict = network_statistics(A)
    btemplist.append(deg_dict["mean"])
    btemplist.append(deg_dict["std_dev"])
    btemplist.append(deg_dict["max"])
    btemplist.append(deg_dict["min"])


    b_scores.append(btemplist)

# get the ith column of a 2D list
def column(matrix, i, k=0):
    # have to start it at 2 because of the way we formatted b_scores
    return [row[i] for row in matrix[k:]]

def calculate_rank(vector):
    # 1 goes to largest element, and then 2 goes to the second largest, etc.
    a = {}
    rank = 1
    rev_sorted_list = sorted(vector)
    rev_sorted_list.reverse()
    for num in rev_sorted_list:
        if num not in a:
            a[num] = rank
            rank = rank + 1
    return[a[i] for i in vector]

# returns vector of ratings
def rank_column(matrix, i):
    col = column(matrix, i, k=2)
    return calculate_rank(col)

# for saving ranks - 1 means largest number, 2 means 2nd largest number, etc.
rank_matrix = []

for i in range(5, 12):
    rank_matrix.append(rank_column(b_scores, i))

# interleaves the scores and the rankings (yes, this should be done programatically)
for i in range(len(b_scores) - 2):
    # first two rows are dead space
    now_row = b_scores[i + 2]
    rank = column(rank_matrix, i, k=0)
    b_scores[i + 2] = now_row[0:6] + [rank[0], now_row[6], rank[1], now_row[7], rank[2], now_row[8], rank[3], now_row[9], rank[4], now_row[10], rank[5], now_row[11], rank[6]] + [now_row[12], now_row[13], now_row[14], now_row[15], now_row[16]]


with open('maup_chicago_intersected.csv', 'w') as csvfile:
    writer = csv.writer(csvfile, delimiter=",")
    writer.writerows(b_scores)
