Code in this folder creates tables and visualizations of the metrics calcualted in `../capy_core`.

Folders and scripts:

+ `latex_tables/`: creates tables used in the Appendix of the paper, showing area values and ranks. Scripts can be configured to rank by various metrics but default to Capy.
+ `line_plots/`: these scripts create metric line plots used in the paper.
+ `rho_vs_metrics_scatterplot/`: create scatterplots showing how areas score on a given metric vs the rho (share of the minority population) in the area. The minority population can be configured to Black or POC (Total - White).
+ `visualization_settings.py`: contains style decisions and helper functions used across the scripts in this folder.