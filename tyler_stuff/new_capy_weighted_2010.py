# for testing the various weighted half edge (and maybe edge) scores...
import numpy as np
import networkx as nx
import json
import csv
import matplotlib.pyplot as plt
import os
import csv

from capy import single_brackets, skew, edge, skew_prime, half_edge, half_edge_infinity, morans_I, dissimilarity, gini, true_half_edge_infinity, standard_dev_of_pop, network_statistics, weighted_half_edge, weighted_edge, true_edge_infinity


# added as of 3/6/19 to match the cities from 1990 and 2000
additional_2010_filenames = ['Ann-Arbor_MI', 'Athens-Clarke-County_GA', 'Bloomington_IN', 'Boulder_CO', 'Bridgeport-Stamford-Norwalk_CT','Burlington-South-Burlington_VT', 'Cedar-Rapids_IA', 'Colorado-Springs_CO','Duluth,MN-WI', 'El-Paso_TX', 'Flint_MI', 'Huntingdon_PA', 'Iowa-City_IA', 'Jacksonville,FL', 'Junction-City_KS', 'Kingsport-Bristol-Bristol_TN-VA', 'Lancaster_PA', 'Lincoln_NE', 'McAllen-Edinburg-Mission_TX', 'Miami-Fort-Lauderdale-West-Palm-Beach_FL', 'New-Haven-Milford_CT', 'Phoenix-Mesa-Scottsdale_AZ', 'Plattsburgh_NY', 'Providence-Warwick_RI-MA', 'Reno_NV', 'Rio-Grande-City_TX', 'San-Antonio-New-Braunfels_TX', 'San-Diego-Carlsbad_CA', 'Santa-Cruz-Watsonville_CA', 'Santa-Fe_NM', 'Savannah_GA', 'Tallahassee_FL', 'Tampa-St-Petersburg-Clearwater,FL', 'Tucson_AZ', 'Tuscaloosa_AL', 'Virginia-Beach-Norfolk-Newport-News,VA-NC']
# I removed 'Ithaca_NY' to get exactly 100 cities

# a subset of the above list, this will be used to make histograms across
names_of_files_for_pop_histogram = ['Flint_MI', 'Miami-Fort-Lauderdale-West-Palm-Beach_FL', 'San-Diego-Carlsbad_CA']

pop_dict = {}

print "this is the file that does the weighted functions"

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
    white = np.zeros((num_vtds,1))
    black = np.zeros((num_vtds,1))
    asian = np.zeros((num_vtds,1))
    hisp = np.zeros((num_vtds,1))

    amein = np.zeros((num_vtds,1))
    natpac = np.zeros((num_vtds,1))
    other = np.zeros((num_vtds,1))
    tot = np.zeros((num_vtds,1))
    nb = np.zeros((num_vtds,1))
    nh = np.zeros((num_vtds,1))
    na = np.zeros((num_vtds,1))
    poc = np.zeros((num_vtds,1))

    #here we add the demographics we want to compute the scores for. Currently we compute the scores for white - demographic and for demographic and its complementary set.
    dems = [black, asian, hisp]
    comps = [nb, na, nh]

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
        white[i] = g.nodes[i]['nhgis00016']
        black[i] = g.nodes[i]['nhgis00017']
        asian[i] = g.nodes[i]['nhgis00019']

        # add up the different variants of hispanic
        hisp[i] =  float(g.nodes[i]['nhgis00023'])

        natpac[i] = g.nodes[i]['nhgis00020']
        other[i] = float(g.nodes[i]['nhgis00018']) +  float(g.nodes[i]['nhgis00021']) + float(g.nodes[i]['nhgis00022'])
        # need to modify
        tot[i] = white[i] + black[i] + asian[i] + hisp[i] + natpac[i] + other[i]
        nb[i] = tot[i] - black[i]
        nh[i] = tot[i] - hisp[i]
        na[i] = tot[i] - asian[i]

        poc[i] = tot[i] - white[i]

    total_white = white.sum()
    total_black = black.sum()
    total_pop = tot.sum()

    white_rho = float(total_white) / float(total_pop) * 100.
    black_rho = float(total_black) / float(total_pop) * 100.

    print "white_rho is " + str(white_rho) + " and black rho is " + str(black_rho)

    # make adjacency matrix
    A = nx.to_numpy_matrix(g)


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
    btemplist.append(true_edge_infinity(poc, white, A))

    # the new weighted versions
    btemplist.append(weighted_edge(poc, white, 0., A))
    btemplist.append(weighted_edge(poc, white, 0.5, A))
    btemplist.append(weighted_edge(poc, white, 2.0, A))
    btemplist.append(weighted_edge(poc, white, 10.0, A))
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
    # I need to tell it to avoid certain names for consistency
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
    white = np.zeros((num_vtds,1))
    black = np.zeros((num_vtds,1))
    asian = np.zeros((num_vtds,1))
    hisp = np.zeros((num_vtds,1))

    amein = np.zeros((num_vtds,1))
    natpac = np.zeros((num_vtds,1))
    other = np.zeros((num_vtds,1))
    tot = np.zeros((num_vtds,1))
    nb = np.zeros((num_vtds,1))
    nh = np.zeros((num_vtds,1))
    na = np.zeros((num_vtds,1))
    poc = np.zeros((num_vtds,1))

    #here we add the demographics we want to compute the scores for. Currently we compute the scores for white - demographic and for demographic and its complementary set.
    dems = [black, asian, hisp]
    comps = [nb, na, nh]

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
        white[i] = g.nodes[i]['NH_WHITE']
        black[i] = g.nodes[i]['NH_BLACK']
        asian[i] = g.nodes[i]['NH_ASIAN']

        # add up the different variants of hispanic
        hisp[i] =  float(g.nodes[i]['H_WHITE']) + float(g.nodes[i]['H_BLACK']) + float(g.nodes[i]['H_ASIAN']) + float(g.nodes[i]['H_NAHI']) + float(g.nodes[i]['H_OTH'])

        natpac[i] = g.nodes[i]['NH_NAHI']
        other[i] = g.nodes[i]['NH_OTH']
        # need to modify
        tot[i] = white[i] + black[i] + asian[i] + hisp[i] + natpac[i] + other[i]
        nb[i] = tot[i] - black[i]
        nh[i] = tot[i] - hisp[i]
        na[i] = tot[i] - asian[i]

        poc[i] = tot[i] - white[i]
    # maybe I can use these vectors, sum them up, etc.
    total_white = white.sum()
    total_black = black.sum()
    total_pop = tot.sum()

    white_rho = float(total_white) / float(total_pop) * 100.
    black_rho = float(total_black) / float(total_pop) * 100.

    print "white_rho is " + str(white_rho) + " and black rho is " + str(black_rho)

    # make adjacency matrix
    A = nx.to_numpy_matrix(g)
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
    btemplist.append(true_edge_infinity(poc, white, A))
    # note - this is the TYPO half edge infinity
    # the new weighted versions
    btemplist.append(weighted_edge(poc, white, 0., A))
    btemplist.append(weighted_edge(poc, white, 0.5, A))
    btemplist.append(weighted_edge(poc, white, 2.0, A))
    btemplist.append(weighted_edge(poc, white, 10.0, A))
    btemplist.append(standard_dev_of_pop(tot))

    # network statistics
    deg_dict = network_statistics(A)
    btemplist.append(deg_dict["mean"])
    btemplist.append(deg_dict["std_dev"])
    btemplist.append(deg_dict["max"])
    btemplist.append(deg_dict["min"])
    b_scores.append(btemplist)

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
b_scores = [[], ["City", "Number of Tracts", "Total polulation", "Percent Black", "Percent White", "Edge" , "Edge rank",  "HEdge", "HEdge rank", "Edge Infinity", "Edge Infinity rank", "Edge 0.", "Edge 0. rank", "Edge 0.5", "Edge 0.5 rank",  "Edge 2", "Edge 2 rank", "Edge 10", "Edge 10 rank", "Population standard deviation", "Degree average", "Degree standard deviation", "Max degree", "Min degree"]] + b_scores
# need to sort out how this ranking works
print "trying starting it at 5, to counter the new column"
for i in range(5, 12):
    rank_matrix.append(rank_column(b_scores, i))
# interleaves the scores and the rankings (yes, this should be done programatically)
for i in range(len(b_scores) - 2):
    now_row = b_scores[i + 2]
    rank = column(rank_matrix, i, k=0)
    b_scores[i + 2] = now_row[0:6] + [rank[0], now_row[6], rank[1], now_row[7], rank[2], now_row[8], rank[3], now_row[9], rank[4], now_row[10], rank[5], now_row[11], rank[6]] + [now_row[12], now_row[13], now_row[14], now_row[15], now_row[16]]
with open('weighted_EDGE_2010_for_4_17_19.csv', 'w') as csvfile:
    writer = csv.writer(csvfile, delimiter=",")
    writer.writerows(b_scores)
