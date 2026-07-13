## This file contains helper methods for the iowa-analysis jupyter notebook

import networkx as nx 
import numpy as np
import matplotlib.pyplot as plt

#this function takes in the demographic and the adjacency matrix and outputs the number of edges between vertices of same demographic
#dem = a vector of that demographic data, where the value at each index is the population of that demographic, each index corresponds to geographic unit
# A = adjacency matrix of dual graph

def double_brackets(dem, A):
    return (np.matmul(dem.T, np.matmul(A + np.identity(A[0].size), dem))[0,0] / 2) 

#this version of same_edges weights the edges that are in the same node by a factor of v, which one can specify below.

def weighted_double_brackets(dem, v, A):
    return (np.matmul(dem.T, np.matmul(A + v*np.identity(A[0].size), dem))[0,0] / 2) 


#this function counts the number of edges between a vertex of demographic x and a vertex of demographic y.
def single_brackets(x, y, A):
    return np.matmul(x.T, np.matmul((A + np.identity(A[0].size)), y))[0,0]

#and the weighted version here, which takes in the same v
def weighted_single_brackets(x, y, v, A):
    return np.matmul(x.T, np.matmul((A + v*np.identity(A[0].size)), y))[0,0]


#the capy score! Will compute a segregation index/cluster energy score between two demographics. 
#Can also adapt to dn (n dimensional) to compute a clustering score between n demographics. 
#Note that one can compare different bins of a same demographic such as race, income, age, but should not compare across demographics.

#dem_list : the list of demographic vectors 
#A : the corresponding adjacency matrix
#return : the happy capy score
    
def capy_edge(dem_list, A):

    num_dems = len(dem_list)
    #same_counts = np.zeros(num_dems)
    numerators = np.zeros(num_dems)
    denominators = np.zeros(num_dems)
 
    result = np.zeros(num_dems)
    for i in range(num_dems):
        denominators[i] += single_brackets(dem_list[i], dem_list[i], A)
        # save computation
        numerators[i] += denominators[i]
        for j in range(num_dems):
            if j is not i:
                denominators[i] += 2*single_brackets(dem_list[i], dem_list[j], A)
    result = np.divide(numerators, denominators)

    return np.sum(result) / 2

def capy_half(dem_list, A):

    num_dems = len(dem_list)
    #same_counts = np.zeros(num_dems)
    numerators = np.zeros(num_dems)
    denominators = np.zeros(num_dems)
 
    result = np.zeros(num_dems)
    for i in range(num_dems):
        denominators[i] += single_brackets(dem_list[i], dem_list[i], A)
        # save computation
        numerators[i] += denominators[i]
        for j in range(num_dems):
            if j is not i:
                denominators[i] += single_brackets(dem_list[i], dem_list[j], A)
    result = np.divide(numerators, denominators)

    return np.sum(result) / 2


def capy_edge_w(dem_list, A):
    num_dems = len(dem_list)
    #same_counts = np.zeros(num_dems)
    numerators = np.zeros(num_dems)
    denominators = np.zeros(num_dems)
 
    result = np.zeros(num_dems)
    for i in range(num_dems):
        denominators[i] += weighted_single_brackets(dem_list[i], dem_list[i], A)
        # save computation
        numerators[i] += denominators[i]
        for j in range(num_dems):
            if j is not i:
                denominators[i] += 2*weighted_single_brackets(dem_list[i], dem_list[j], A)
    result = np.divide(numerators, denominators)

    return np.sum(result) / 2

def capy_half_w(dem_list, A):

    num_dems = len(dem_list)
    #same_counts = np.zeros(num_dems)
    numerators = np.zeros(num_dems)
    denominators = np.zeros(num_dems)
 
    result = np.zeros(num_dems)
    for i in range(num_dems):
        denominators[i] += weighted_single_brackets(dem_list[i], dem_list[i], A)
        # save computation
        numerators[i] += denominators[i]
        for j in range(num_dems):
            if j is not i:
                denominators[i] += weighted_single_brackets(dem_list[i], dem_list[j], A)
    result = np.divide(numerators, denominators)

    return np.sum(result) / 2

def draw_state(dual_graph, demvec, repvec, pos, node_size):
    value_map = []
    for i in range(dual_graph.number_of_nodes()):
        if demvec[i] == 0 and repvec[i] == 0:
            value_map.append(0.5)
        else:
            value_map.append((repvec[i]/(demvec[i] + repvec[i])))
    value_map = np.array(value_map)
    plt.figure(num=None, dpi=300, facecolor='w', edgecolor='k')

    nx.draw_networkx(dual_graph, pos=pos, node_size=node_size, with_labels=False, cmap=plt.get_cmap('cool'), \
                     node_color=value_map, vmin=0, vmax=1, width=0.1)
    plt.show()

# determine if the one cluster is actually one cluster
def valid_one_cluster(g, xvec):
	# check that both the population X and Y subgraphs are connected
	X_nodes = []
	Y_nodes = []
	i=0
	for node in g.nodes():
		if xvec[i] >0:
			X_nodes.append(node)
		else:
			Y_nodes.append(node)
		i+=1

	if (nx.number_connected_components(g.subgraph(X_nodes)) == 1) and (nx.number_connected_components(g.subgraph(Y_nodes)) == 1):
		return True
	else:
		return False

# determine that the isolated config is actually isolated
def valid_isolated_config(g, xvec):
    nodes_in_cluster = []
    i=0
    for node in g.nodes():
        if xvec[i] >0:
            nodes_in_cluster.append(node)
        i+=1
    
    # should have as many connected components as there are nonzero entries
    if nx.number_connected_components(g.subgraph(nodes_in_cluster)) == np.count_nonzero(xvec):
        return True
    else:
        return False
    