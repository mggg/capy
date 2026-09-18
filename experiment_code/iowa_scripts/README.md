Code in this folder simulates population distributions of two groups, x and y, on the counties of Iowa.  
The ideal configurations are:
+ Checkerboad: half the nodes are all x the other half are all y and neither x or y nodes have neighbours of the same type
+ Isolated: each node is either all x or all y and x nodes have no x neighbours
+ Clustered: nodes are either all x and all y and the subgraph of x nodes forms a single component
+ kClustered: nodes are either all x and all y and the subgraph of x nodes has number of components greater than one and less than or equal to k.
+ Constant: each node contains $\rhoM$ members of group x and $(1-\rho)M$ group y, where M is the node's total population

##Folders and scripts:
+ `make_iowa-files.py/` Creates the Iowa counties dual graph used in all scripts by fetching  2010 and 2020 Census PL 94-171 data. All scripts use 2020 data by default. The data is stored in data/experiment_specific/ia_files.
+ `make_kclustered_iowa_plots.py` Creates kclustered Iowa configurations. Plots scatterplots of both capy and moran against rho an arbitrary number of times (currently 500) for an arbitrary number of target rhos (currently 100). 
+ `make_clustered_iowa_plots/`  Creates clustered Iowa configurations. Plots scatterplots of both capy and moran against rho an arbitrary number of times (currently 500) for an arbitrary number of target rhos (currently 100). 
+ `make_iowa_isol_plots/` Creates isolated Iowa configurations. Plots scatterplots of both capy and moran against rho an arbitrary number of times (currently 500) for an arbitrary number of target rhos (currently 100).
+ `make_uniform_iowa_plots/` Creates uniform Iowa configurations. Plots scatterplots of both capy and moran against rho an arbitrary number of times (currently 500) for an arbitrary number of target rhos (currently 100).

All random scripts use random.seed(42). Achieved group shares (real_rho) will generally differ from target shares because the BFS-based population assignment adds whole counties at a time using actual TOTPOP values — the algorithm stops when the next county would overshoot the target, so exact targets are rarely hit. All scatterplots plot using real rho and all  Supplied figures reflect this stochastic process under seed 42; re-runs with the same seed should reproduce them, but results may differ if the order of nodes returned by the graph library changes across versions.

##Reproducing Figures
All scripts must be run from the repository root. The supplied
`data/experiment_specific/ia_files/ia_counties_2020.json` supports all four plotting scripts —
no Census API key is needed.

###Plotting Figures
```bash
mkdir -p figures/iowa
python experiment_code/iowa_scripts/make_uniform_iowa_plots.py
python experiment_code/iowa_scripts/make_isol_iowa_plots.py
python experiment_code/iowa_scripts/make_clustered_iowa_plots.py
python experiment_code/iowa_scripts/make_kclustered_iowa_plots.py
```

###Rebuilding Data (Census API Key Required)
To rebuild the data runn 
```bash
export CENSUS_API_KEY=<your_key>
python experiment_code/iowa_scripts/make_iowa_files.py
```

## Summary of Script Inputs and Outputs
| Script | Input | Outputs in `figures/iowa/` |
|---|---|---|
| `make_uniform_iowa_plots.py` | `ia_counties_2020.json` | `capy_by_rho_uniform_iowa.png`, `uniform_iowa_visualization_rho=<rho>.png`, `divergent_rho_colorbar_rho=<rho>.png` |
| `make_isol_iowa_plots.py` | `ia_counties_2020.json` | `capy_by_rho_isol_iowa.png`, `moran_by_rho_isol_iowa.png`, `isol_iowa_visualization_rho=<real_rho>.png` |
| `make_clustered_iowa_plots.py` | `ia_counties_2020.json` | `capy_by_rho_onecluster_iowa.png`, `moran_by_rho_onecluster_iowa.png`, `onecluster_iowa_visualization_rho=<real_rho>.png` |
| `make_kclustered_iowa_plots.py` | `ia_counties_2020.json` | `capy_by_rho_multicluster_iowa_k=<num_start_nodes>.png`, `moran_by_rho_multicluster_iowa_k=<num_start_nodes>.png`, `multicluster_iowa_visualization_rho=<real_rho>_k=<num_start_nodes>_numcomponents=<num_components>.png` |
| `make_iowa_legend.py` | *(none)* | `iowa_population_size_legend.png`, `iowa_population_composition_legend.png` |
| `make_iowa_files.py` | Census API (`CENSUS_API_KEY`) | `ia_counties_2020.json`, `ia_counties_2020.shp`, `ia_counties_2010.json`, `ia_counties_2010.shp` |

Note: to make figures renderable in latex, periods in decimals have been replaced with the letter p.