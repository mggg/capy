# Assortativity grids

This experiment compares Capy and Moran's I across synthetic grids with low, medium, and high clustering. Run the simulation first, then generate the figures:

```bash
poetry run python experiment_code/assortativity_grids/scripts/simulate_grid_metrics.py
poetry run python experiment_code/assortativity_grids/scripts/plot_grids_and_metric_histogram.py
```

`simulate_grid_metrics.py` generates 10,000 grids for each of the three clustering levels, for 30,000 grids total. The editable `N_GRIDS` and `BASE_SEED` constants near the top of the script control the sample count and random seeds. The simulation writes:

```text
experiment_code/assortativity_grids/scripts/simulations/metrics_results.json
experiment_code/assortativity_grids/scripts/simulations/exemplar_grids.json
```

`plot_grids_and_metric_histogram.py` reads both JSON files and writes the clustering examples, metric-distribution histograms, and standalone legend under:

```text
figures/assortativity_grids/
```

Shared grid construction and metric helpers live under `utils/`.
