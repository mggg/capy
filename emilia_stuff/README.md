# capy
clustering propensity scores for demographic segregation

Work flow:

From the city shapefiles, which are an intersection of city boundaries (2013): https://www.census.gov/geo/maps-data/data/cbf/cbf_msa.html
and demographic DP1 tract shapefiles: https://www.census.gov/geo/maps-data/data/tiger-data.html

we make jsons which contain all adjacency information between tracts and all the population demographic populations at each node (tract). This is done with the demographic_dual_loop script, which calls the make_graph script. 

The capy1105 contains all methods, including edge, half edges (and both their weighted counterparts), dissimilarity, frey, assortativity, moran's I, and gini, the latter one however is taking upwards of 3 hours to run so it's currently commented out. 

Finally, the scores are saved in csv files and the plots are generated. 

Total population and rho are all currently hard coded based on the shapefile data. 
