This folder contains the scripts used to run and visualize the major analyses in the paper. The core pipeline is configured in `capy_core/config.yaml` and run with `scripts/reproduce.sh`. Each experiment has its own README for subsequent commands.

Folders and Scripts

+ `baseline/`: contains code to visualize all plots based on the metro area data produced in capy-core.
+ `iowa_scripts/`: plots metrics on idealized population configurations of the county dual graph of Iowa.
+ `observed_diffusion/`: contains the analysis of empirical clusters of black population in Philadelphia and Chicago
+ `assortativity_grids/`: calculates capy and moran scores on grids of low, medium, and high assortativity
+ `grid_figs_scripts/`: contains the code for all analyses on grids including, scores on idealized configurations of asymptotically large grids, scores on idealized configurations on 90x90 grids, and the analysis of synthetic diffusion.
