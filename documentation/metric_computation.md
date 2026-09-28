# Compute segregation metrics

## Contents

- [Run the stage](#run-the-stage)
- [Use individual metric functions](#use-individual-metric-functions)
- [Populations and spatial weights](#populations-and-spatial-weights)
- [Metric names and formulas](#metric-names-and-formulas)
- [Sources and formula correspondence](#sources-and-formula-correspondence)
- [Undefined values](#undefined-values)
- [Saved tables and yearly averages](#saved-tables-and-yearly-averages)
- [Following the code](#following-the-code)

## Run the stage

Once graph archives exist, calculate their metrics directly from the ZIPs:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml compute-metrics
```

The small example produces scores for Delaware's three county study areas using 2020 tract graphs.
Use `code/configs/replication.yaml` for the paper's national CBSA results, or
`code/configs/max_city.yaml` for the selected-city results. This stage reads only graph archives;
raw downloads and intermediate population, geography, and membership tables are not needed.

Graph inputs may be an original single ZIP or a complete set of numbered parts. The stage
discovers parts automatically, checks their combined area inventory, and reads each graph from its
recorded archive. It still writes one metric table per year and level. See
[archive parts](graph_construction.md#archive-parts-and-repackaging) for naming and conversion.

By default, every supported metric is calculated for both `white_black` and `white_poc`. Set
`metric_names` or `population_comparisons` in the YAML to restrict those choices, using the names
below. The [commented configuration](../code/configs/example.yaml) lists all options. Years,
levels, study-area type, and definition vintage select archives under `graph_archive_directory`.
Raw-file selection patterns do not filter the contents of an existing graph archive.

An area progress bar appears for each archive. The two distance-weighted Moran scores evaluate
every pair of nodes, so they can take substantially longer on block graphs. Distances are
calculated in batches to bound temporary memory, but the number of pairs still grows
quadratically. The stage runs one graph at a time; `max_parallel_downloads` does not control
metric computation.

## Use individual metric functions

The functions in `capy_metrics` work independently of the replication pipeline. Each score has an
array or matrix interface and a graph interface ending in `_from_graph`. Both are public and
return one floating-point score. Graph functions accept ordinary NetworkX graphs, including
GerryChain graphs, and take population attribute names rather than assuming the study's column
names.

For example, this computes Moran's I from custom attributes on a small graph:

```python
import networkx as nx
from capy_metrics import MoranWeightType, morans_I_from_graph

graph = nx.path_graph(["a", "b", "c"])
nx.set_node_attributes(graph, {"a": 2, "b": 7, "c": 4}, "group1")
nx.set_node_attributes(graph, {"a": 10, "b": 12, "c": 20}, "total")

score = morans_I_from_graph(
    graph, "group1", "total", MoranWeightType.ROW_STANDARDIZED
)
```

Run from an environment with `code/` on the Python import path, for example `PYTHONPATH=code uv run
--locked python your_analysis.py` from the repository root. To reuse prepared inputs across
computations, call the numerical functions directly:

```python
import numpy as np
from capy_metrics import build_csr_adjacency_matrix, build_moran_weights, morans_I

adjacency = build_csr_adjacency_matrix(graph)
weights = build_moran_weights(adjacency, MoranWeightType.ROW_STANDARDIZED)
group_population = np.array([2, 7, 4])
total_population = np.array([10, 12, 20])
score = morans_I(weights, group_population / total_population)
```

Matrix rows, matrix columns, and population vectors must use the same node order. The graph helpers
use graph iteration order, including when labels are mixed types. `morans_I()` accepts a CSR matrix,
a CSR array, or a dense weight matrix and uses its weights as supplied. It does not construct or
row-standardize them. For inverse-distance scores, use `distance_morans_I(coordinates, shares,
distance_power=1)` or `distance_power=2`. That function retains bounded distance batches; its graph
counterpart accepts the distance choices in `MoranWeightType` and optional centroid attribute names.
Graph coordinates must share a projected coordinate system, but the reusable functions do not
require the pipeline's specific CRS.

| Numerical function                                 | Inputs after any leading matrix argument                          |
| -------------------------------------------------- | ----------------------------------------------------------------- |
| `morans_I(weights, shares)`                        | Group population divided by the chosen total                      |
| `dissimilarity(group, total)`                      | Group counts and totals including that group                      |
| `theil_information(group, total)`                  | Group counts and totals including that group                      |
| `relative_diversity(group, total)`                 | Group counts and totals including that group                      |
| `aspatial_capy(first, second)`                     | Two disjoint groups' counts                                       |
| `capy(adjacency, first, second, lam=1)`            | Two disjoint groups' counts, including quadratic self-pairs       |
| `capy_exact(adjacency, first, second, lam=1)`      | Two disjoint groups' integer counts, excluding self-pairs         |
| `edge_assortativity(adjacency, group, total)`      | Group counts and totals for relative-majority classification      |
| `half_edge_assortativity(adjacency, group, total)` | The same counts, with same-class edges contributing two endpoints |

For D, H, and R, supply `spatial_weights=` to evaluate local-environment shares while retaining
original population weights. Omitting it gives the aspatial index. The same optional argument
works on their graph functions, with weights in graph node order. No functions alter the input
graph, counts, or matrices, and none requires connectedness merely because the pipeline uses
connected graphs. Adjacency graph functions require undirected simple graphs without self-loops.
Isolated rows in row-standardized adjacency remain zero, and Moran's normalization uses the weight
mass that remains. A weight matrix with no nonzero entries gives an undefined score.

Lambda is a finite, nonnegative **neighbor weight** in $W=I+\lambda A$; within-unit weight stays
one. For example:

```python
from capy_metrics import aspatial_capy, capy, capy_exact

second_population = total_population - group_population
aspatial = aspatial_capy(group_population, second_population)
weighted = capy(adjacency, group_population, second_population, lam=2)
exact = capy_exact(adjacency, group_population, second_population, lam=2)
```

At `lam=0`, the quadratic function equals `aspatial_capy()`. The exact function still removes
self-pairs and therefore need not equal it. Lambda is available through these public functions;
the pipeline keeps its existing fixed metric choices and does not add YAML parameter sweeps.

Malformed inputs raise `ValueError`, while a missing graph attribute raises `KeyError`. When valid
inputs have no defined score, the function raises `UndefinedMetricError`, whose `reason`
identifies the limitation. The pipeline catches that exception per score and saves the reason with
a null value, preserving other valid results. Direct callers can catch it in the same way:

```python
from capy_metrics import UndefinedMetricError

try:
    score = morans_I(weights, group_population / total_population)
except UndefinedMetricError as error:
    print(error.reason.value)
```

## Populations and spatial weights

For each comparison, let $x_i$ be the non-Hispanic White population and $y_i$ the Black or POC
population of unit $i$. The population universe is $t_i=x_i+y_i$, with $T=\sum_i t_i$, unit share
$p_i=x_i/t_i$, and overall share $\rho=\sum_i x_i/T$. White–Black calculations therefore use the
combined White and Black population, while White–POC calculations use total population. See the
[population guide](population_processing.md#population-definitions-and-checks) for the source
definitions.

Both comparisons use the same connected graph, whose units satisfy `WHITE + BLACK > 0`. Any POC
population removed by that filter stays excluded from White–POC metrics. The saved graph
accounting reports that loss; a metric does not silently restore those residents or treat them as
zero.

Let $A$ be the binary adjacency matrix with zero diagonal. All saved edges participate, including
artificial connections, and no edge is weighted by shared boundary length. Local-environment
shares use a unit together with its neighbors:

$$\widetilde p_i=\frac{((I+A)x)_i}{((I+A)t)_i}.$$

Distance weights instead use all pairs of distinct nodes and their saved geometric centroids in
ESRI:102003. These centroids can lie outside the polygons, as explained in the [graph
guide](graph_construction.md#centroid-coordinates-for-distance-based-metrics). Self-distances
receive weight zero; coincident centroids of distinct units make both distance scores undefined.

## Metric names and formulas

We use ordinary and weighted inner-product notation throughout:

$$
\langle u,v\rangle=\sum_i u_i v_i, \qquad
\langle u,v\rangle_W=\langle u,Wv\rangle.
$$

The weighted brackets denote this pairing even when $W$ is not positive definite. The formulas
below specify the conventions implemented here, including the distinct-person correction for
spatial Capy.

### Evenness and local-environment scores

These six scores use the two-group, discrete forms of Reardon and O'Sullivan's
[_Measures of Spatial Segregation_ (2004)](https://doi.org/10.1111/j.0081-1750.2004.00150.x).
Their equations (6)–(12), pp. 139–140, supply the formulas, and the text below equation (6)
identifies the aspatial special case. Their population integrals become sums over our units;
choosing $I+A$ as the local environment is a study decision. The public functions allow broader
nonnegative weight matrices, including nonsymmetric ones outside the paper's proximity
assumptions.

Write $h(s)=-s\log s-(1-s)\log(1-s)$ and $j(s)=2s(1-s)$, with $0\log0=0$.

| Saved metric name            | Definition                                             |
| ---------------------------- | ------------------------------------------------------ |
| `dissimilarity`              | $D=\sum_i(t_i/T)\lvert p_i-\rho\rvert/[2\rho(1-\rho)]$ |
| `theil_information`          | $H=1-\sum_i(t_i/T)h(p_i)/h(\rho)$                      |
| `relative_diversity`         | $R=1-\sum_i(t_i/T)j(p_i)/j(\rho)$                      |
| `spatial_dissimilarity`      | $D$ with $p_i$ replaced by $\widetilde p_i$            |
| `spatial_theil_information`  | $H$ with $p_i$ replaced by $\widetilde p_i$            |
| `spatial_relative_diversity` | $R$ with $p_i$ replaced by $\widetilde p_i$            |

Dissimilarity measures the difference between the groups' distributions across units. Without
smoothing, it also equals $\tfrac12\sum_i|x_i/X-y_i/Y|$, where $X$ and $Y$ are group totals. Theil
information compares average local entropy with the entropy of the whole population. Relative
diversity makes the analogous comparison using the probability that two independent population
draws belong to different groups. For each aspatial score, zero means identical local and overall
compositions, while one means each populated unit contains only one group.

The spatial scores answer those questions about local environments instead of individual units.
The spatial versions keep the original weights $t_i/T$ and overall share $\rho$. Neighborhoods can
overlap and have different sizes, so their smoothed shares need not average to $\rho$ under those
weights. Spatial $H$ and $R$ can consequently be negative; values are not clipped. The paper also
discusses negative values on p. 132, footnote 5. Natural logarithms replace its base-two
logarithms in our two-group $H$, with no numerical effect because the base factor cancels.

### Capy scores

For same-group totals $a,c$ and between-group total $b$, the reported score is the mean of X-skew
and Y-skew:

$$C=\frac12\left(\frac{a}{a+b}+\frac{c}{c+b}\right).$$

| Saved metric name | Pair totals                                                                                                    |
| ----------------- | -------------------------------------------------------------------------------------------------------------- |
| `aspatial_capy`   | $a=\langle x,x\rangle$, $b=\langle x,y\rangle$, $c=\langle y,y\rangle$                                         |
| `capy_exact`      | $a=\langle x,x\rangle_{I+A}-\sum_i x_i$, $b=\langle x,y\rangle_{I+A}$, $c=\langle y,y\rangle_{I+A}-\sum_i y_i$ |

Aspatial Capy, $C_0$, includes quadratic self-pairs and equals one-half when every unit has the
same composition. The second score counts distinct people, with equal
weight on within-unit and neighboring-unit interactions. Its same-group totals count ordered
pairs, or twice the number of same-group edges in the exploded graph. Subtracting the population
removes self-pairs; there is no corresponding subtraction from the between-group inner product.

These conventions differ even on a single unit. With one White and one Black resident, quadratic
within-unit Capy is one-half, while exact distinct-person Capy is zero because the only available
neighbor has the other type. The pipeline uses these two fixed choices. Public Capy functions
additionally accept finite nonnegative neighbor weights through `lam`.

### Moran scores

Moran scores measure association between deviations of unit shares, using a matrix to decide which
pairs count and by how much. They center shares across units, so a small unit and a large unit
have equal influence on the centering step. This differs from the population-weighted regional
share used by the evenness scores.

For all variants, $z_i=p_i-\operatorname{mean}(p)$ uses the **unweighted mean of unit shares**.
The reported expression is based on the weighted definition in
[Anselin's GeoDa workbook](https://geodacenter.github.io/workbook/5a_global_auto/lab5a.html#morans-i),
with the signed-weight qualification below:

$$I_W=\frac{n}{\sum_{ij}|W_{ij}|}\frac{\langle z,z\rangle_W}{\langle z,z\rangle}.$$

Except for the negative Laplacian, weights are nonnegative, so absolute normalization equals the
usual sum of weights. The negative Laplacian has signed sum zero; its absolute normalization is an
explicit separate convention, not the ordinary Moran statistic applied unchanged. A negative
Laplacian measures squared differences across edges with a negative sign; unlike the nonnegative
weight versions, it cannot give positive spatial association. These weight matrices therefore
produce different statistics and should not be interpreted as interchangeable estimates.

| Saved metric name                | Weight matrix                                                                               |
| -------------------------------- | ------------------------------------------------------------------------------------------- | ------- | --- |
| `moran_adjacency`                | $W=A$                                                                                       |
| `moran_with_self`                | $W=I+A$                                                                                     |
| `moran_row_standardized`         | $W_{ij}=A_{ij}/d_i$, where $d_i$ is node degree                                             |
| `moran_negative_laplacian`       | $W=A-\operatorname{diag}(d)$, normalized by $\sum                                           | W\_{ij} | $   |
| `moran_metropolis`               | Adjacent off-diagonal weights $1/\max(d_i,d_j)$; each diagonal completes its row sum to one |
| `moran_inverse_distance`         | Off-diagonal $1/\operatorname{distance}(i,j)$, then divide each row by its sum              |
| `moran_inverse_squared_distance` | Off-diagonal $1/\operatorname{distance}(i,j)^2$, then divide each row by its sum            |

The adjacency variant counts each edge equally. Row standardization instead gives each
non-isolated unit equal outgoing weight, reducing the influence of high-degree units. The
self-inclusive variant adds each unit's own squared deviation to the numerator, changing the usual
no-self-neighbor statistic. Metropolis weights make connections to high-degree nodes weaker and
use diagonal weights to complete each row to one. The Metropolis matrix matches
[Xiao and Boyd (2004)](https://web.stanford.edu/~boyd/papers/pdf/fastavg.pdf), section 4.2, p. 70,
and equation (18), p. 69; using it in a segregation statistic is our application.

The two distance variants row-standardize all off-diagonal inverse distances, with no distance
cutoff. Squaring the inverse distance makes nearby units relatively more influential. These
choices, the use of population shares, and the centroid convention belong to this implementation;
a citation for Moran's statistic does not establish them as choices made in the original paper.

### Relative-majority assortativity

Each unit joins the first class when its White share is at least the overall White share $\rho$;
all other units join the second class. This threshold is relative to the selected population
comparison, rather than a fixed 50% threshold. Let $e_{XX},e_{XY},e_{YY}$ count undirected graph
edges within or between those classes.

| Saved metric name         | Definition                                                   |
| ------------------------- | ------------------------------------------------------------ |
| `edge_assortativity`      | $\frac12[e_{XX}/(e_{XX}+e_{XY})+e_{YY}/(e_{YY}+e_{XY})]$     |
| `half_edge_assortativity` | $\frac12[2e_{XX}/(2e_{XX}+e_{XY})+2e_{YY}/(2e_{YY}+e_{XY})]$ |

The edge score averages the fraction of each class's incident edges that stay within the class,
counting an internal edge once. The half-edge score instead counts endpoints, so an internal edge
contributes twice. Both scores are zero when all connections cross classes and one when every
connection stays within a class, provided both class denominators are positive.

The half-edge score equals $(1+r)/2$ for binary attribute assortativity $r$ on these unit classes,
using [Newman (2003)](https://arxiv.org/pdf/cond-mat/0209450), equation (2), section II.A. It is a
transformed coefficient, not the value $r$ reported in the paper. The edge score uses a different
denominator and is a study-specific score; it is not Newman's coefficient. Neither is
population-weighted Capy: classes are assigned to whole units, and their graph connections are
counted without exploding populations into individual people. The calculation leaves graph
attributes unchanged.

## Sources and formula correspondence

The citations identify the expressions being implemented, not a claim that every weight choice or
transformation originated in the cited work.

| Scores                                            | Source and exact correspondence                                                                                                                                                                             |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- | ------------------------------------------------------------------------------------------- |
| Dissimilarity and spatial dissimilarity           | Reardon and O'Sullivan (2004), equation (12), p. 140. Two groups give equal absolute deviations; their regional diversity is $2\rho(1-\rho)$, producing the denominator above.                              |
| Theil information and spatial Theil information   | Same paper, equations (6)–(8), p. 139. Discrete population-weighted entropy replaces the integral; the logarithm base cancels.                                                                              |
| Relative diversity and spatial relative diversity | Same paper, equations (9)–(11), pp. 139–140. Its interaction diversity becomes $2p(1-p)$ for two groups.                                                                                                    |
| All six nonnegative-weight Moran scores           | Anselin (2020), _Global Spatial Autocorrelation (1)_, “Concept / Moran's I,” gives $n \langle z,z\rangle_W/(S_0\langle z,z\rangle)$ with $S_0=\sum W_{ij}$. The matrices listed above specify our variants. |
| Metropolis matrix within Moran                    | Xiao and Boyd (2004), section 4.2, p. 70: $1/\max(d_i,d_j)$ on edges. Equation (18), p. 69, supplies the diagonal. This is not the alternative $1/(1+\max(d_i,d_j))$ convention.                            |
| Negative-Laplacian score                          | A project-defined extension: $W=A-\operatorname{diag}(d)$ and $S_0=\sum                                                                                                                                     | W\_{ij} | $. The ordinary signed sum is zero, so the standard Moran formula cannot be used unchanged. |
| Half-edge assortativity                           | Newman (2003), equation (2), section II.A, gives categorical $r$. Our binary specialization reports $(1+r)/2$, with a study-defined population-share threshold.                                             |
| Edge assortativity                                | A study-specific mean of edge fractions. The different denominator prevents attributing this formula to Newman's coefficient.                                                                               |

For the half-edge correspondence, put $a=2e_{XX}$, $b=e_{XY}$, $c=2e_{YY}$, and $S=a+2b+c$.
Newman's mixing matrix is $E=\left(\begin{smallmatrix}a&b\\b&c\end{smallmatrix}\right)/S$, with
row marginals $q_X=(a+b)/S$ and $q_Y=(b+c)/S$. Substituting into his formula gives

$$
r=\frac{\operatorname{tr}(E)-(q_X^2+q_Y^2)}{1-(q_X^2+q_Y^2)}
=1-\frac{bS}{(a+b)(b+c)},
$$

whereas our mean endpoint fraction is

$$
\frac12\left(\frac{a}{a+b}+\frac{c}{b+c}\right)
=1-\frac{bS}{2(a+b)(b+c)}=\frac{1+r}{2}.
$$

This identity holds for unequal class sizes and unequal degree totals, provided both endpoint
marginals are positive. It does not identify the edge-count variant with $r$.

The sources are:

- Reardon, S. F., and O'Sullivan, D. (2004).
  [_Measures of Spatial Segregation_](https://doi.org/10.1111/j.0081-1750.2004.00150.x).
  _Sociological Methodology_ **34**, 121–162. Equations (1)–(2), p. 129, define local shares; pp.
  130 and 139 explain the aspatial special case. The graph-unit interpretation here is a discrete
  specialization.
- Anselin, L. (2020 revision).
  [_Global Spatial Autocorrelation (1)_](https://geodacenter.github.io/workbook/5a_global_auto/lab5a.html#morans-i).
  _GeoDa Workbook_, “Concept / Moran's I.” This gives the general weighted expression.
- Xiao, L., and Boyd, S. (2004).
  [_Fast linear iterations for distributed averaging_](https://web.stanford.edu/~boyd/papers/pdf/fastavg.pdf).
  _Systems & Control Letters_ **53**, 65–78.
  [DOI](https://doi.org/10.1016/j.sysconle.2004.02.022).
- Newman, M. E. J. (2003).
  [_Mixing patterns in networks_](https://arxiv.org/pdf/cond-mat/0209450). _Physical Review E_
  **67**, 026126. [DOI](https://doi.org/10.1103/PhysRevE.67.026126). Equations (1)–(2) appear on
  p. 2 of the linked author version.

## Undefined values

Undefined scores are saved as null, with one of the following reasons. Other valid scores for the
same graph remain available.

| `undefined_reason`        | Meaning                                                                                  |
| ------------------------- | ---------------------------------------------------------------------------------------- |
| `no_graph`                | The graph stage recorded no graph; `graph_status` preserves its specific reason.         |
| `absent_population_group` | One comparison group has no residents, making an evenness denominator zero.              |
| `no_pair_interactions`    | A group has no eligible pairs for its Capy skew.                                         |
| `zero_share_variance`     | Every unit has the same share, so Moran's denominator is zero.                           |
| `no_neighbors`            | The requested spatial weights have zero total absolute weight.                           |
| `absent_majority_class`   | Every unit is in the same relative-majority class.                                       |
| `coincident_centroids`    | Distinct nodes have identical centroid coordinates, preventing inverse-distance weights. |

For a single-node graph, Moran scores are undefined, while evenness and Capy may remain defined.
If several limitations apply, the first applicable check supplies the reason. Malformed graphs,
missing archives, inconsistent population accounting, and unexpected computation failures stop the
run. They are not converted into mathematical undefined values.

## Saved tables and yearly averages

Outputs live beneath `metric_results_directory`, followed by study-area type and definition year.
For the small example, the default location is `results/metrics/county/2020/`:

- `2020_tracts.parquet` has one row per area, population comparison, and metric. Columns identify
  the area, Census year, geography level, comparison, metric, value, undefined reason, and graph
  status. Other selections produce one file per year and level.
- `graph_outcomes.parquet` copies the selected archives' area accounting, including retained and
  removed population, and adds each archive's filename.
- `average_when_all_years_present.parquet` contains unweighted yearly area means, the expected
  years, the number of contributing areas, and their identifiers.

Each mean uses a fixed set of areas with a defined value in **every selected, supported year**,
separately for each metric, comparison, and resolution. Thus one metric's undefined value does not
remove the area from another metric's sample. For a 1980–2020 run, county and tract means require
all five years; block and block-group means require 1990–2020 because 1980 boundaries are
unavailable. An empty sample produces a null mean. No population-size threshold is applied here;
publication figures may require an additional, explicitly chosen sample restriction.

Reruns replace the metric tables for that study-area type and vintage, including results for years
or metrics removed from the configuration. Use a different `metric_results_directory` to keep two
runs. Year/level tables are saved as they finish, while the means are written last. If a run
fails, it can leave completed year/level files but no means file; rerun the stage after fixing the
input.

## Following the code

[`capy_metrics/`](../code/capy_metrics/) contains reusable functions organized by metric family.
Graph functions live beside their numerical counterparts, and neither depends on study
configuration or output tables. Shared input checks cover array shapes, numeric counts, and matrix
alignment; the formulas retain their own mathematical conditions.

[`calculate_scores.py`](../code/capy_core/compute_metrics/calculate_scores.py) is the pipeline
adapter. It chooses the study's comparisons, prepares requested adjacency weights once per graph,
and calls only selected numerical functions. Distance scores evaluate their batches independently.
[`run_metrics.py`](../code/capy_core/compute_metrics/run_metrics.py) selects archives, checks
graph accounting, and writes results. Finally,
[`summarize_years.py`](../code/capy_core/compute_metrics/summarize_years.py) builds the
fixed-sample means. The stage checks archive inventories and population accounting without
repeating upstream boundary, membership, or adjacency construction checks.
