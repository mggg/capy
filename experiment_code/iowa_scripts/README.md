Code in this folder simulates population distributions of two groups, x and y, on the counties of Iowa.  
The ideal configurations are:
+ Checkerboad: half the nodes are all x the other half are all y and neither x or y nodes have neighbours of the same type
+ Isolated: each node is either all x or all y and x nodes have no x neighbours
+ Clustered: nodes are either all x and all y and the subgraph of x nodes forms a single component
+ kClustered: nodes are either all x and all y and the subgraph of x nodes and forms less than or equal to k components
+ Constant: each node contains $\rhoM$ members of group x and $(1-\rho)M$ group y, where M is the node's total population

Folders and scripts:
+ `generate_kclustered_iowa_plots.py` Creates kclustered Iowa configurations. Plots scatterplots of both capy and moran against rho an arbitrary number of times (currently 500) for an arbitrary number of target rhos (currently 100). The current code for clustered configurations attempts to populate Iowa to meet a certain target rho, however it usually overshoots. The scatterplots use the real rho.
+ `make_clustered_iowa_plots/`  Creates kclustered Iowa configurations. Plots scatterplots of both capy and moran against rho an arbitrary number of times (currently 500) for an arbitrary number of target rhos (currently 100). The current code for clustered configurations attempts to populate Iowa to meet a certain target rho, however it usually overshoots. The scatterplots use the real rho.
+ `make_iowa-files.py/` Creates the Iowa counties dual graph used in all scripts. The data is stored in data/experiment_specific/ia_files.
+ `make_iowa_isol_plots/` Creates isolated Iowa configurations. Plots scatterplots of both capy and moran against rho an arbitrary number of times (currently 500) for an arbitrary number of target rhos (currently 100).
+ `make_uniform_iowa_plots/` Creates isolated Iowa configurations. Plots scatterplots of both capy and moran against rho an arbitrary number of times (currently 500) for an arbitrary number of target rhos (currently 100).