

All my visualization scripts are in the folder Reproduction/Reproduction_Notebooks and all my output images are in Reproduction/Reproduction_Figures.

**Data**
Only Iowa and lambda rankings use external data

Iowa: the data gets pulled from the census and processed through Reproduction/Reproduction_Notebooks/iowa_scripts/make_iowa_files.py and stored in reproduction_data/ia_files.

Lambda Rankings: this just uses the main data produced by the pipeline

**Viz Families**
There are four visualization folders in Reproduction/Reproduction_Figures. All except the diffusion folder correspond to figures in CLUSTERING PROPENSITYData and Democracy Labhttps://mggg.org › Capy

Reproduction/Reproduction_Figures/lambda_rankings (figure B3 in the preprint): these show the rankings of the top 100 metro areas by level of segregation for Capy compared to the rankings of weighted variants. I have one image comparing Capy to lambda values of [0, 0.5, 2, 10, infinity] and one comparing them just to [0, infinity] (which I thought would be less visually confusing while getting the point across). These images use a jitter (by user random amounts up to a user specified threshold in the x and y directions)

The next three folders all color nodes or polygons by rho. For this I have a diverging colorbar that diverges at rho with high node rho values yellow and low node rho values blue. An example of this colorbar is found at Reproduction/Reproduction_Figures/Iowa/divergent_rho_colorbar_rho=0.3.png. Currently it is diverging at $\rho = \frac{X}{T}$ where X is the global x population and T is the total population. Perhaps it should be the population unweighted average of tract nodes $= (\sum_i \rho_i)/n$ where n is the number of nodes and $\rho_i = x_i /t_i$ where $x_i, t_i$ are the x population and total population respectively of node i. This later value is not what most of the paper means by rho but it is what Moran’s I sees.

Reproduction/Reproduction_Figures/idealized_grids_diffusion (this is produced from the same scripts folder as the idealized grids, it does not correspond to anything in the preprint): These show deterministic diffusion from an initial configuration of all x nodes to a final uniform state. In each step of diffusion first the diffused region expands to include all neighbours and then the population of the is redistributed so that group x is uniformly distributed in the diffused region. It visualizes all steps and plots three metrics (capy, Moran, dissimilarity) by step for five different initial configuation.

Reproduction/Reproduction_Figures/Idealized_Grids (figure 4 in the preprint): 
This shows plots of capy versus rho on idealized clustered, checkerboard, isolated, and uniform configurations on asymptotically large grid. 

(Moon said we should probably drop the below plots in favor of iowa)
It also shows how capy responds to idealized configurations on 90x90 grids, specifically:
	-Capy versus rho on deterministic checkerboard and uniform grid configurations (few datapoints)
	-Capy versus rho for many samples on probabilistic single cluster, multi cluster, and isolated grid configurations
	-Plots visualizations of all five idealized configs on 90x90 grids with rho = .3

Reproduction/Reproduction_Figures/Iowa (figure 6 in the preprint):
This shows scatterplots plots of moran and capy versus rho on and visualizes the following idealized configurations of iowa:
	-One random cluster
	-Multiple random clusters 
	-Isolated configurations (Each node is either all x or all y and x nodes have no x nodes neighbours)
	-the x population is uniformly distributed across all nodes
