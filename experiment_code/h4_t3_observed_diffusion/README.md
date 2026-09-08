# H4 T3: Observed diffusion

This experiment measures changes in the mass and spread of four Black
population clusters:

- Chicago CBSA (`16980`): Hyde Park and Austin
- Philadelphia CBSA (`37980`): west of Germantown Avenue and West Philadelphia - need to confirm is these are the clusters we need
- Adding other clusters as needed

It uses the existing tract network in `data/rpocessed/dual_graphs/YEAR` graphs for 1980, 1990, 2000, 2010, and 2020. Network distance is unweighted shortest-path length, measured in tract-adjacency edges.

## Current extent of cluster definition

Take the graph of a city and create a subgraph by removing every node whose black share is below rho. On this new subgraph, take the two connected components that have the highest number of nodes. These are the two clusters for the city. To reflect it back to previous years. Let any tract that is at least 50% covered by the cluster be part of the cluster for that year.

## Metrics

### Cluster medoid
For a search area $A$, Black population in a tract $B_i$, and graph distance $d(i,j)$: we go over all nodes $j$ in the area and find the $j$ with minimum $i$-distance * $Black_i$ population. This $j$ is the medoid:

$$
m = \operatorname*{arg\,min}_{j \in A}
\sum_{i \in A} B_i d(i,j)
$$

$m$ is recalculated independently in every decade.

### Mass

Mass is just the $\sum(B_i)$ in the area.

### Spread

Spread is the mean distance from the medoid over all $B_i$:

$$
\frac{\sum_i B_i d(i,m)}{\sum_i B_i}
$$

