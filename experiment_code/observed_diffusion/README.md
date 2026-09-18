# Observed diffusion

This experiment measures changes in the mass and spread of four Black population clusters within `tracts_in_max_city` Census-place boundaries:

- Chicago, Census place code `1714000`: South Side and Austin
- Philadelphia, Census place code `4260000`: Germantown and West Philadelphia

It uses tract boundaries and full-city graphs for 1980, 1990, 2000, 2010, and 2020. Network distance is unweighted shortest-path length, measured in tract-adjacency edges.

## Data prerequisite

The experiment requires `tracts_in_max_city` clipped geographies and dual graphs for all five years and both place codes. Configure the run in [`capy_core/config.yaml`](../../capy_core/config.yaml):

```yaml
study_area_type: max_city
census_geography_type: tracts
census_geography_years:
  - 2020
  - 2010
  - 2000
  - 1990
  - 1980
study_area_vintage: 2020
```

[`capy_core/config.py`](../../capy_core/config.py) resolves these YAML settings for the shell pipeline. Generate the required data from the repository root with:

```bash
bash scripts/reproduce.sh
```

See [`scripts/reproduce.sh`](../../scripts/reproduce.sh) for the pipeline stages. The required boundaries are written under `data/shared/processed/clipped_geographies/<year>/`, and the graphs under `data/shared/processed/dual_graphs/<year>/`.

### Expected boundary and graph files

For each year in 1980, 1990, 2000, 2010, and 2020, and for each place code (`1714000` and `4260000`), the experiment expects these files:

```text
data/shared/processed/clipped_geographies/<year>/
    tracts_in_max_city_<place_code>_<year>_march_2020_vintage.gpkg

data/shared/processed/dual_graphs/<year>/
    tracts_in_max_city_<place_code>_<year>_march_2020_vintage_connected.json
    tracts_in_max_city_<place_code>_<year>_march_2020_vintage_orig.json
```

The cluster calculation uses the connected graphs. The plotting script uses the original graphs and the clipped boundary files.

## Run order

From the repository root, calculate cluster membership and metrics first:

```bash
poetry run python experiment_code/observed_diffusion/scripts/cluster_backprojection_with_buffers.py
```

This writes `auto_cluster_tracts.csv` and `auto_cluster_metrics.csv` under `data/experiment_specific/observed_diffusion_data/`. Then generate the figures:

```bash
poetry run python experiment_code/observed_diffusion/scripts/plot_choropleth_radial_and_lines.py
```

Figures are written under `figures/observed_diffusion/metrics_panels_by_buffers/`.

### Using the supplied cluster results

The repository includes `auto_cluster_tracts.csv` and `auto_cluster_metrics.csv` under `data/experiment_specific/observed_diffusion_data/`. To reproduce figures from these supplied results, skip `cluster_backprojection_with_buffers.py` and run the plotting command directly.

Plotting still requires the full-city clipped boundaries and `_orig.json` graphs listed above for both cities and all five years. The archived cluster subgraphs under `data/experiment_specific/observed_diffusion_data/cluster_graphs/` contain only selected cluster nodes; they cannot replace the full-city boundaries or graphs.

## Cluster construction and back-projection

The implementation constructs and tracks clusters as follows:

1. For each tract in the 2020 city graph, calculate the Black share among Black and White residents. The threshold is the unweighted arithmetic mean of these tract shares, so each tract contributes equally regardless of population.
2. Select tracts whose Black share is strictly greater than that mean. In their induced adjacency graph, the two components with the most tracts become the two initial clusters.
3. Expand each initial cluster by 0 through 10 graph edges in the 2020 city graph. For each buffer size, dissolve the selected tract polygons and fill interior polygon holes while retaining disconnected pieces.
4. Apply each buffered polygon separately to 1980, 1990, 2000, 2010, and 2020. A tract is selected when strictly more than 50% of its area overlaps the buffered polygon.

The calculation uses the 2020 cluster shapes for every target year, including 2020, so tract selection follows the same area-overlap rule in every decade.

## Metrics

### Cluster medoid
For a search area $A$, Black population in a tract $B_i$, and graph distance $d(i,j)$: we go over all nodes $j$ in the area and find the $j$ with minimum $i$-distance * $Black_i$ population. This $j$ is the medoid:

$$
m = \operatorname*{arg\,min}_{j \in A}
\sum_{i \in A} B_i d(i,j)
$$

Graph-distance and Euclidean medoids are calculated separately for each cluster and decade at buffer 0. Graph distance is unweighted shortest-path distance in tract-adjacency edges; Euclidean distance is measured between tract centroids. Each medoid minimizes the distance to cluster tracts weighted by their Black populations. The buffer-0 medoids are then held fixed while the buffer grows from 1 through 10, preventing the centers from drifting as tracts are added.

### Mass

Mass is just the $\sum(B_i)$ in the area.

### Spread

Spread is the mean distance from the medoid over all $B_i$:

$$
\frac{\sum_i B_i d(i,m)}{\sum_i B_i}
$$
