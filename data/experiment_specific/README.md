
+ `ia_files\` Shapefiles of Iowas counties for 2010 and 2020 with demographic census data attributes as well as jsons of the dual graphs. They are produced in`experiment_code/iowa_scripts/make_iowa_files.py\`
+ `observed_diffusion/` Contains data describing the two larges majority black clusters in Chicago and Philadelphia. 
    + `auto_cluster_tracts.csv` a list of tracts in each cluster by buffer size by year (produced by experiment_code/h4_t3_observed_diffusion/scripts/cluster_backprojection_with_buffers.py)
    + `auto_cluster_metrics.csv` metrics calculated on each cluster by buffer size by year (produced by experiment_code/h4_t3_observed_diffusion/scripts/cluster_backprojection_with_buffers.py)
    + `cluster_graphs` json dual graphs of each cluster by year (was produced by currently archived code)
