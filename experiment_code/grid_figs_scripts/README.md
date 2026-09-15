This folder contains code to reproduce all figures produced on the analysis of polygonal grids.

Most scripts simulate population distributions of two groups, x and y, on both 90x90 grids and asymptotic grids and analyzes segregation metrics on them.  
The ideal configurations are: 
+ Checkerboad: half the nodes are all y the other half have x populations equal to $2M\rho$ where, all the neighbours of nodes of one type are of the other type
+ Isolated: each node is either all x or all y and x nodes have no x neighbours
+ Clustered: nodes are either all x and all y and the subgraph of x nodes forms a single component
+ kClustered: nodes are either all x and all y and the subgraph of x nodes and forms less than or equal to k components
+ Constant: each node contains $\rhoM$ members of group x and $(1-\rho)M$ group y, where M is the node's total population

It also simulates diffusion of the x population from initial configurations and plots segregation metrics over the course of the process

Folders and scripts:
+ 'fig-4_plot_grid_asymptotics.py' Plots lineplots of capy versus rho for checkerboard, isolated, clustered, and constant configurations on an asymptotically large nxn polygonal grid.
+ 'fig-4_plot_metric_on_deterministic_ideal_configs_on_90x90_grids.py' Plots lineplots of vapy versus rho on the checkerboard and constant configurations (both of which are deterministic versus rho)
+ 'fig-4_plot_metric_on_random_ideal_configs_on_90x90_grids.py' Plots scatterplots of capy versus rho on the isolated, clustered, and kclustered configurations for an arbirtrary number of samples of an arbitrary number of rhos.
+ 'fig-5_visualize_ideal_90x90_grid_configs.py' visualizes isolated, clusters, multiple clusters, and checkerboard configurations on a 90x90 polygonal grid

