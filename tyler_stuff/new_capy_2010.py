# for downloading city values from 2000
# Tyler Piazza 1/24/19
import numpy as np
import networkx as nx
import json
import csv
import matplotlib.pyplot as plt
import os
import csv

from capy import single_brackets, skew, edge, skew_prime, half_edge, half_edge_infinity, morans_I, dissimilarity, gini, true_half_edge_infinity, standard_dev_of_pop, network_statistics, remove_dummy_tracts

# added as of 3/6/19 to match the cities from 1990 and 2000
additional_2010_filenames = ['Ann-Arbor_MI', 'Athens-Clarke-County_GA', 'Bloomington_IN', 'Boulder_CO', 'Bridgeport-Stamford-Norwalk_CT','Burlington-South-Burlington_VT', 'Cedar-Rapids_IA', 'Colorado-Springs_CO','Duluth,MN-WI', 'El-Paso_TX', 'Flint_MI', 'Huntingdon_PA', 'Iowa-City_IA', 'Jacksonville,FL', 'Junction-City_KS', 'Kingsport-Bristol-Bristol_TN-VA', 'Lancaster_PA', 'Lincoln_NE', 'McAllen-Edinburg-Mission_TX', 'Miami-Fort-Lauderdale-West-Palm-Beach_FL', 'New-Haven-Milford_CT', 'Phoenix-Mesa-Scottsdale_AZ', 'Plattsburgh_NY', 'Providence-Warwick_RI-MA', 'Reno_NV', 'Rio-Grande-City_TX', 'San-Antonio-New-Braunfels_TX', 'San-Diego-Carlsbad_CA', 'Santa-Cruz-Watsonville_CA', 'Santa-Fe_NM', 'Savannah_GA', 'Tallahassee_FL', 'Tampa-St-Petersburg-Clearwater,FL', 'Tucson_AZ', 'Tuscaloosa_AL', 'Virginia-Beach-Norfolk-Newport-News,VA-NC']
# I removed 'Ithaca_NY' to get exactly 100 cities

# a subset of the above list, this will be used to make histograms across
names_of_files_for_pop_histogram = ['Flint_MI', 'Miami-Fort-Lauderdale-West-Palm-Beach_FL', 'San-Diego-Carlsbad_CA']

pop_dict = {}
CSA_code_dict = {}

# first get a dictionary of CSA codes
with open('CSA_Codes.csv' , 'rU') as csvfile:
    csvreader = csv.reader(csvfile)
    for row in csvreader:
        if row[0] != "Metro Area" and row[0]:
            code = row[0]
            code = code[0 : len(code) - 3]
            CSA_code_dict[row[1]] = code

b_scores = []
h_scores = [[]]
a_scores = [[]]


bEdge = []
bHEdge = []
bDiss = []
bFrey = []
bAssort = []
bMoran = []


print "******************************************************"
print "at the additional stuff"
print "******************************************************"
# duplicate information, just with the other things for 2010

print "be sure you have the right list here for what you are doing"
for city in additional_2010_filenames:
    print (city)

    with open('json2010new/'+city+'_data.json') as f:
        data = json.load(f)
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

    # for 2010, for the newer cities
    """
    #H7Z001 - nhgis00014:      Total
    H7Z002 - nhgis00015:      Not Hispanic or Latino
    H7Z003 - nhgis00016:      Not Hispanic or Latino: White alone
    H7Z004 - nhgis00017:      Not Hispanic or Latino: Black or African American alone
    H7Z005 - nhgis00018:      Not Hispanic or Latino: American Indian and Alaska Native alone
    H7Z006 - nhgis00019:      Not Hispanic or Latino: Asian alone
    H7Z007 - nhgis00020:      Not Hispanic or Latino: Native Hawaiian and Other Pacific Islander alone
    H7Z008 - nhgis00021:      Not Hispanic or Latino: Some Other Race alone
    H7Z009 - nhgis00022:      Not Hispanic or Latino: Two or More Races
    H7Z010 - nhgis00023:      Hispanic or Latino
    H7Z011 - nhgis00024:      Hispanic or Latino: White alone
    H7Z012 - nhgis00025:      Hispanic or Latino: Black or African American alone
    H7Z013 - nhgis00026:      Hispanic or Latino: American Indian and Alaska Native alone
    H7Z014 - nhgis00027:      Hispanic or Latino: Asian alone
    H7Z015 - nhgis00028:      Hispanic or Latino: Native Hawaiian and Other Pacific Islander alone
    H7Z016 - nhgis00029:      Hispanic or Latino: Some Other Race alone
    H7Z017 - nhgis00030:      Hispanic or Latino: Two or More Races
    """
    n_tracts = g.number_of_nodes()
    if n_tracts <= 30:
        print "NUMBER OF TRACTS IS LOW: " + str(n_tracts)
        continue
    # assign demographic population per geographic unit
    for i in range(n_tracts):
        # I assume that each category is discrete (there are no people in multiple categories)
        old_white[i] = g.nodes[i]['nhgis00016']
        old_black[i] = g.nodes[i]['nhgis00017']
        old_asian[i] = g.nodes[i]['nhgis00019']

        # add up the different variants of hispanic
        old_hisp[i] =  float(g.nodes[i]['nhgis00023'])


        old_natpac[i] = g.nodes[i]['nhgis00020']
        old_other[i] = float(g.nodes[i]['nhgis00018']) +  float(g.nodes[i]['nhgis00021']) + float(g.nodes[i]['nhgis00022'])
        # need to modify
        old_tot[i] = old_white[i] + old_black[i] + old_asian[i] + old_hisp[i] + old_natpac[i] + old_other[i]
        old_nb[i] = old_tot[i] - old_black[i]
        old_nh[i] = old_tot[i] - old_hisp[i]
        old_na[i] = old_tot[i] - old_asian[i]

        old_poc[i] = old_tot[i] - old_white[i]

    total_white = old_white.sum()
    total_black = old_black.sum()
    total_pop = old_tot.sum()

    white_rho = float(total_white) / float(total_pop) * 100.
    black_rho = float(total_black) / float(total_pop) * 100.

    print "white_rho is " + str(white_rho) + " and black rho is " + str(black_rho)

    # make adjacency matrix
    A = nx.to_numpy_matrix(g)

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
    # done rehandling adjacency, dummy tracts, etc.
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
    # note: this is the real half edge infinity
    btemplist.append(true_half_edge_infinity(poc, white, A))
    # note - this is the TYPO half edge infinity
    btemplist.append(half_edge_infinity(poc, white, A))
    btemplist.append((dissimilarity(poc, tot)[0]))
    btemplist.append((gini(poc, tot)[0]))
    btemplist.append(morans_I(poc, A))
    # for standard deviations
    btemplist.append(standard_dev_of_pop(tot))

    # network statistics
    deg_dict = network_statistics(A)
    btemplist.append(deg_dict["mean"])
    btemplist.append(deg_dict["std_dev"])
    btemplist.append(deg_dict["max"])
    btemplist.append(deg_dict["min"])

    b_scores.append(btemplist)


print "******************************************************"
print "at the directory stuff"
print "******************************************************"

for filename in os.listdir("2010_JSONS"):
    #print filename
    city = CSA_code_dict[filename]
    print (city)
    if "Jackson-Yazoo" in city or "Johnson City" in city or "San Juan" in city:
        print "************located city that we are ignoring for consistency with other files************"
        continue

    with open('2010_JSONS/'+filename) as f:
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

    # for 2000, from the codebook (and then the second code is what is in the shapefiles)
    # I am ignoging 007 and 014 for now
    # not hispanic
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
    for i in range(g.number_of_nodes()):
        # I assume that each category is discrete (there are no people in multiple categories)
        old_white[i] = g.nodes[i]['NH_WHITE']
        old_black[i] = g.nodes[i]['NH_BLACK']
        old_asian[i] = g.nodes[i]['NH_ASIAN']

        # add up the different variants of hispanic
        old_hisp[i] =  float(g.nodes[i]['H_WHITE']) + float(g.nodes[i]['H_BLACK']) + float(g.nodes[i]['H_ASIAN']) + float(g.nodes[i]['H_NAHI']) + float(g.nodes[i]['H_OTH'])
        """
        hisp_w[i] = g.nodes[i]['H_WHITE']
        hisp_b[i] = g.nodes[i]['H_BLACK']
        hisp_a[i] = g.nodes[i]['H_ASIAN']
        hisp_n[i] = g.nodes[i]['H_NAHI']
        hisp_o[i] = g.nodes[i]['H_OTH']
        """

        old_natpac[i] = g.nodes[i]['NH_NAHI']
        old_other[i] = g.nodes[i]['NH_OTH']
        # need to modify
        old_tot[i] = old_white[i] + old_black[i] + old_asian[i] + old_hisp[i] + old_natpac[i] + old_other[i]
        old_nb[i] = old_tot[i] - old_black[i]
        old_nh[i] = old_tot[i] - old_hisp[i]
        old_na[i] = old_tot[i] - old_asian[i]

        old_poc[i] = old_tot[i] - old_white[i]

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
    # done rehandling adjacency, dummy tracts, etc.
    #compute and store the energy scores in a csv
    btemplist = []
    # info, like name, population, black rho, and white rho (percentage of that pop in the city)
    btemplist.append(city)
    # append number of tracts
    btemplist.append(n_tracts)
    btemplist.append(total_pop)
    btemplist.append(black_rho)
    btemplist.append(white_rho)

    # now compute interesting scoprs
    btemplist.append(edge(poc, white, A))
    btemplist.append(half_edge(poc, white, A))
    # note: this is the real half edge infinity
    btemplist.append(true_half_edge_infinity(poc, white, A))
    # note - this is the TYPO half edge infinity
    btemplist.append(half_edge_infinity(poc, white, A))
    btemplist.append((dissimilarity(poc, tot)[0]))
    btemplist.append((gini(poc, tot)[0]))
    btemplist.append(morans_I(poc, A))
    # for standard deviations
    btemplist.append(standard_dev_of_pop(tot))
    # network statistics
    deg_dict = network_statistics(A)
    btemplist.append(deg_dict["mean"])
    btemplist.append(deg_dict["std_dev"])
    btemplist.append(deg_dict["max"])
    btemplist.append(deg_dict["min"])
    b_scores.append(btemplist)

# just get a column from a matrix, offset by k
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
    # the k here used to be 2, but I have since removed
    col = column(matrix, i, k=2)
    return calculate_rank(col)

# for saving ranks - 1 means largest number, 2 means 2nd largest number, etc.
rank_matrix = []

# sort by city names
b_scores = sorted(b_scores)
# appending the info that the other things have
b_scores = [[], ["City", "Number of Tracts", "Total polulation", "Percent Black", "Percent White", "Edge" , "Edge rank",  "HEdge", "HEdge rank", "HEdgeInfinity (True)", "HEdgeInfinity (True) rank", "Typo HEI", "Typo HEI rank", "Dissimilarity", "Dissimilarity rank",  "Gini", "Gini rank", "Moran's I", "Moran's I rank", "Population standard deviation", "Degree average", "Degree standard deviation", "Max degree", "Min degree"]] + b_scores

for i in range(5, 12):
    rank_matrix.append(rank_column(b_scores, i))

# interleaves the scores and the rankings (yes, this should be done programatically)
for i in range(len(b_scores) - 2):
    now_row = b_scores[i + 2]
    rank = column(rank_matrix, i, k=0)
    b_scores[i + 2] = now_row[0:6] + [rank[0], now_row[6], rank[1], now_row[7], rank[2], now_row[8], rank[3], now_row[9], rank[4], now_row[10], rank[5], now_row[11], rank[6]] + [now_row[12], now_row[13], now_row[14], now_row[15], now_row[16]]

with open('2010_for_4_23_2019_no_dummies.csv', 'w') as csvfile:
    writer = csv.writer(csvfile, delimiter=",")
    writer.writerows(b_scores)


