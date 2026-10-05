# Grid, diffusion, and geographic experiments

These experiments examine how segregation scores respond to population arrangements, diffusion,
and neighborhood change. `code/run_experiment.py` computes the results, and `code/make_figures.py`
draws figures from the saved tables and arrays. Rendering is separate from computation, so visual
changes do not require new simulations or score calculations. The
[national figure guide](figures.md) covers analyses of national pipeline results.

The command examples assume the repository root as the working directory. Each figure component is
saved as a separate 300 dpi PNG, with legends and colorbars in their own files. Titles and axis
labels are left to LaTeX assembly.

## Contents

- [Saved-table conventions](#saved-table-conventions)
- [Grid arrangements and reference curves](#grid-arrangements-and-reference-curves)
- [Reardon–O’Sullivan lattice examples](#reardonosullivan-lattice-examples)
- [Expanding-support diffusion](#expanding-support-diffusion)
- [Stochastic diffusion](#stochastic-diffusion)
- [Iowa county configurations](#iowa-county-configurations)
- [Neighborhood change](#neighborhood-change)
- [Paths and plot adjustments](#paths-and-plot-adjustments)

## Saved-table conventions

The two-row examples below use saved results, with decimal values rounded to four places. To keep
wide tables readable, the previews omit some columns that are explained in the accompanying text,
including geometry and inherited source attributes in geographic tables. A displayed `null` means
the saved value is missing.

Load ordinary tables with `pandas.read_parquet()` and geographic tables with
`geopandas.read_parquet()`, using the named identity columns to distinguish rows because writers
omit the pandas index. Preserve geographic identifiers as text so leading zeros survive. Years,
steps, and counts still represent integers if nullable columns load as floating point. Shares are
fractions and scores are dimensionless, with `group_share` measuring first-group population or
mass as a fraction of the combined two-group total.

The **shared scores** used by most computed experiments are `dissimilarity`, `entropy_index`,
`relative_diversity`, their `spatial_` counterparts, `aspatial_capy`, `capy` (or `capy_exact`),
`moran_with_self`, and `moran_row_standardized`. Each score occupies its own column and is paired
with `<metric>_undefined_reason`: a numeric score leaves the reason null while an undefined score
leaves the value null and records the explanation. The
[metric guide](national_pipeline/06_metric_computation.md) gives the formulas and reason codes.

## Grid arrangements and reference curves

The grid experiments compare scores for controlled spatial arrangements on square lattices. The
Reardon–O’Sullivan triangular-lattice examples have their own section below.

```bash
uv run --locked python code/run_experiment.py \
    grid-reference-scores grid-pop-share-arrangements grid-score-comparisons
uv run --locked python code/make_figures.py \
    grid-reference-scores grid-pop-share-arrangements grid-score-comparisons
```

`grid-reference-scores` computes score curves for clustered, constant, isolated, and checkerboard
arrangements of continuous population mass on a square lattice with four neighbors per interior
cell. The clustered curves describe large-region limits. For isolated arrangements, density alone
cannot determine spatial dissimilarity, information, or relative diversity, so those curves are
omitted. Gray shading identifies reference regions for the lattice arrangements shown, without
establishing universal bounds for irregular graphs. Where curves coincide, their exact values are
preserved and line styles distinguish them.

`grid-pop-share-arrangements` combines three population-share distributions with three spatial
arrangements to produce nine grids. `grid-score-comparisons` creates six variants per combination,
producing 54 share examples, alongside sixty binary grids with 72 people of each group. The binary
classes have 30–50, 120–145, or 210–235 unlike-neighbor edges. Every example has overall
population share 0.5, so its point lies on that vertical line in a score-versus-share plot. The
saved score table identifies the population distribution, arrangement, sample, and category.
Preparation also saves the reference scores, which remain fixed until the next preparation run.

These square-grid workflows save results under `results/experiments/grid_configurations/` and
images under `figures/grid_configurations/`, in a folder named for each experiment. The score
comparison images are further divided into `grids/` and `scores/`, with legends beside the score
plots.

`grid-distributions` describes the score distributions of randomized binary arrangements:

```bash
uv run --locked python code/run_experiment.py grid-distributions --samples 10000 --seed 20260918
uv run --locked python code/make_figures.py grid-distributions
```

Here, `--samples` sets the number of grids per clustering class. Preparation retains both the
sampled scores and representative grids, which the renderer uses for histograms and arrangement
images. Each cell contains 100 people of one group, so these scores use regular Capy. By contrast,
the one-person-per-node binary examples use exact Capy. Fractional population masses also use
regular Capy even when the masses sum to one per node.

Distribution results live under `results/experiments/grid_configurations/distributions/`. Images
in `figures/grid_configurations/distributions/` identify the clustering class and plot type, for
example `grid_low_clustering.png` and `low_clustering_capy_histogram.png`.

### Saved grid tables and arrays

Paths in this section begin at `results/experiments/grid_configurations/`.

#### Reference curves: `grid_reference_scores/theoretical_scores.parquet`

| `arrangement` | `metric`      | `group_share` | `value` |
| ------------- | ------------- | ------------- | ------- |
| cluster       | dissimilarity | 0.0050        | 1       |
| cluster       | dissimilarity | 0.0060        | 1       |

Here, the clustered arrangement has limiting dissimilarity one at both displayed first-group
shares. A row locates one point on that analytic curve through `arrangement`, `metric`, and
`group_share`, then records the score in `value`. The other arrangement families are `constant`,
`isolated`, and `checkerboard`, evaluated by default at 500 share coordinates from 0.005 through
0.5. Constant Moran and isolated spatial evenness curves have no rows because their values are
undefined or cannot be determined from share alone.

#### Share arrangements: `grid_pop_share_arrangements/share_scores.parquet`

| `example`          | `seed`   | `group_share` | `capy` | `moran_row_standardized` |
| ------------------ | -------- | ------------- | ------ | ------------------------ |
| moderate_clustered | 20260918 | 0.5000        | 0.6161 | 0.9120                   |
| moderate_random    | 20260918 | 0.5000        | 0.5178 | -0.0752                  |

These rows compare two 12×12 grids with the same overall first-group share of 0.5 but different
spatial arrangements. Their `example` names combine a distribution (`moderate`, `many_mixed`, or
`mostly_mixed`) with an arrangement (`clustered`, `random`, or `alternating`), identifying both
the score row and its array in `share_grids.npz`. The saved `seed` records the random stream used
to construct the arrangements. Although the preview shows only Capy and row-standardized Moran,
the table retains all shared scores and their reason columns for inspection. Rendering uses the
corresponding arrays.

#### Score comparisons: `grid_score_comparisons/grid_scores.parquet`

| `example`             | `family` | `category` | `arrangement` | `sample` | `capy` | `capy_exact` |
| --------------------- | -------- | ---------- | ------------- | -------- | ------ | ------------ |
| moderate_clustered_01 | shares   | moderate   | clustered     | 1        | 0.6161 | null         |
| binary_few_unlike_01  | binary   | few_unlike | null          | 1        | null   | 0.8332       |

The comparison table brings share and binary grids together, with `example` linking each score row
to a 12×12 array in `grid_arrays.npz`. In the first row, `family = shares` makes `category` the
population-share distribution and `arrangement` its spatial ordering. In the binary family,
`category` instead names the edge-count class (`few_unlike`, `intermediate`, or `many_unlike`),
leaving `arrangement` null. Within each combination, `sample` numbers the examples from one.

The different Capy columns follow from what the grids represent: continuous shares use regular
`capy` whereas one-person-per-node binary assignments use `capy_exact`. A null in the unused
column therefore means that convention was not computed for the row. When a computed score is
mathematically undefined, its reason column supplies an explanation. In addition to these fields,
the full table retains `seed`, `group_share`, and the remaining shared scores with their reasons.

#### Comparison references: `grid_score_comparisons/reference_scores.parquet`

| `arrangement` | `metric`      | `group_share` | `value` |
| ------------- | ------------- | ------------- | ------- |
| cluster       | dissimilarity | 0.0050        | 1       |
| cluster       | dissimilarity | 0.0060        | 1       |

These rows use the same curve-point format as `theoretical_scores.parquet` above. This copy is
saved alongside the comparison grids so the renderer uses the references from their preparation
run. It joins curve points by metric, not by grid `example`.

#### Sampled distributions: `distributions/distribution_scores.parquet`

| `kind` | `seed` | `capy` | `moran_row_standardized` |
| ------ | ------ | ------ | ------------------------ |
| high   | 1000   | 0.8783 | 0.6950                   |
| high   | 1001   | 0.8957 | 0.7350                   |

Each row is one sampled 10×10 binary arrangement. `kind` is its clustering class (`low`, `medium`,
or `high`), and `seed` identifies the sample within that class. The two numeric columns hold its
scores. This table has no reason columns. The histogram renderer groups rows by `kind`.
`distribution_examples.npz` stores the first sampled grid of each class under the corresponding
class name. Its zero/one cells denote which group occupies the cell, with 100 people per cell.

## Reardon–O’Sullivan lattice examples

This experiment reproduces the published triangular-lattice population arrangements and compares
scores under finite and periodic interpretations. Each dot represents one person. The finite
interpretation scores the printed window while the periodic interpretation repeats its pattern
across the boundaries. Although rendering produces only the four printed-arrangement panels, the
saved score table contains both interpretations.

```bash
uv run --locked python code/run_experiment.py triangular
uv run --locked python code/make_figures.py triangular
```

The experiment saves scores and arrays under `results/experiments/reardon_osullivan/` and images
under `figures/reardon_osullivan/`. It requires no national pipeline inputs. The `triangular`
command prepares or renders this experiment independently of the square-grid workflows.

### Saved lattice tables and arrays

`triangular_scores.parquet` contains observations such as:

| `panel`    | `interpretation` | `period_rows` | `period_columns` | `white_exposure_to_black` | `capy_exact` |
| ---------- | ---------------- | ------------- | ---------------- | ------------------------- | ------------ |
| upper_left | printed          | 12            | 10               | 0.1446                    | 0.4140       |
| upper_left | periodic         | 12            | 10               | 0.1485                    | 0.4227       |

The two rows score the same `upper_left` panel under `printed` and `periodic` interpretations, so
their differing values reflect the treatment of the pattern’s boundaries. Together, `panel` and
`interpretation` identify a result, with `upper_right`, `lower_left`, and `lower_right` completing
the panel set. The saved pattern’s dimensions appear in `period_rows` and `period_columns`: these
describe the printed array or the repeating tile. For the periodic `upper_right` panel, scoring
repeats the 2×3 tile into a 4×3 graph so all six neighbors remain distinct. The
`white_exposure_to_black` column gives the White-population-weighted mean local Black share.
Remaining fields include `group_share` and the shared scores, taking Black as the first group and
using exact Capy.

`triangular_windows.npz` contains display arrays keyed by `<interpretation>_<panel>`, such as
`printed_upper_left`. Each is 12×10, with one for a Black person and zero for a White person. The
renderer reads these windows, whose dimensions can differ from the scoring period.

## Expanding-support diffusion

The `expanding-support` experiment separates spatial spreading from population growth or decline.
It starts with a pure first-group region on a 20×20 grid and spreads that group's mass uniformly
over a growing set of occupied cells. Cells outside this support have zero first-group share.

```bash
uv run --locked python code/run_experiment.py expanding-support
uv run --locked python code/make_figures.py expanding-support
```

The experiment uses three starting shapes. A centered 10×10 rectangle expands by alternating
horizontal and vertical bands. A 5×5 core expands by rook steps, adding cells that share an edge
with the occupied region. A thick cross starts with 99 occupied cells and follows the same
rook-distance rule.

Each shape has constant, growth, and decline variants while every cell retains total mass one. For
the rectangle and cross, growth ends at overall first-group share 0.4 and decline at 0.1. The
smaller core instead ends at 0.1 and 0.025, respectively. Overall shares change linearly with step
for the rectangle and core, and with occupied area for the cross. Within the occupied region, each
cell's first-group share equals the overall share divided by the occupied fraction of the grid.

The dissimilarity, entropy, and Capy plots overlay the three demographic variants. A separate
Moran comparison uses closed-neighborhood and row-standardized weights. Within a shape, scaling
all cell shares by a common multiplier leaves Moran unchanged. Moran is undefined on the final
uniform grid, so that endpoint remains a gap in the plot.

Each shape has a folder under `results/experiments/synthetic_diffusion/expanding_support/`,
containing `states.npz` and `expanding_support_scores.parquet`. The corresponding folder under
`figures/synthetic_diffusion/expanding_support/` contains snapshots, score plots, legends, and a
colorbar. Shape folders use names such as `centered_rectangle` and `rook_expanding_core`.

### Saved expanding-support format

For example, `centered_rectangle/expanding_support_scores.parquet` contains:

| `shape`            | `demography` | `step` | `support_fraction` | `group_share` | `capy` |
| ------------------ | ------------ | ------ | ------------------ | ------------- | ------ |
| centered_rectangle | constant     | 0      | 0.2500             | 0.2500        | 0.9459 |
| centered_rectangle | constant     | 1      | 0.3000             | 0.2500        | 0.8460 |

Between the two displayed steps, occupied area grows from 25% to 30% while the overall first-group
share remains 25%. The distinction is recorded by `support_fraction`, which measures occupied
cells, and `group_share`, which measures population mass. Each trajectory is identified by `shape`
and `demography`, with zero-based integer `step` locating a row along it. The shape matches the
folder name, and demography is `constant`, `growth`, or `decline`.

The full table also records `expansion_progress = step / (number_of_steps - 1)` and the shared
scores using regular `capy`. At the final uniform grid, Moran values become null and their reason
columns explain the undefined result.

`states.npz` stores first-group share arrays keyed by `<shape>_<demography>`, in
`(step, row, column)` order. Shapes are `(11, 20, 20)` for the rectangle and cross and
`(17, 20, 20)` for the rook core. A table row's `step` indexes the matching array directly. The
second group's mass is one minus the saved share in each cell. Plotting reads both files.

## Stochastic diffusion

The stochastic workflow combines supplied replicate score histories with newly simulated snapshot
examples. Its source CSVs live under `scripts/synthetic/stochastic_data/` within the directory
specified by `--moon-source-directory`.

```bash
uv run --locked python code/run_experiment.py stochastic \
    --moon-source-directory /path/to/moon-capy/code/capy_deck_replication
uv run --locked python code/make_figures.py stochastic
```

Preparation reads the two long-run score CSVs from that source. It saves complete histories for
the early interval, their medians and pointwise 10th–90th percentile bands, and independent seeded
snapshot trajectories. The supplied replicate scores are reused without recomputing them with the
current metric functions. Once preparation finishes, rendering needs only the saved results.

Every cell initially contains 1,000 people. The central 10×10 square is entirely the first group,
and other cells are entirely the second. At each step, a person moves to a uniformly chosen rook
neighbor with probability 0.2. One-sided diffusion moves only the first population while two-sided
diffusion moves both. First-group births or deaths follow movement: growth doubles expected
first-group population over 4,000 steps, and decline reduces it to one third. The plotted interval
ends at step 800 but uses those same rates.

Snapshots at steps 0, 25, 100, 250, 500, and 800 show independent examples rather than replicate
medians. The NPZ file stores these step coordinates alongside the population arrays. Separate
images show group share and first-group counts. To keep a common count scale, colors saturate at
1,000.

The supplied one-sided results have 25 complete early replicates per variant. Two-sided constant
and growth have 23 each, and decline has 22. A decline replicate ending at step 518 is excluded
throughout the interval, with the exclusion recorded in `source_replicate_coverage.parquet`.
Results live under `results/experiments/synthetic_diffusion/stochastic/one_sided/` and
`two_sided/`, each containing score tables, replicate coverage, and snapshot arrays. Figures use
the same movement subfolders under `figures/synthetic_diffusion/stochastic/`, with legends and
colorbars beside the plots.

### Saved stochastic format

Each movement folder contains the following tables. The text fields describe the scenario, with
`movement` set to `one_sided` or `two_sided` and `demography` set to `constant`, `growth`, or
`decline`.

#### Replicate histories: `stochastic_scores.parquet`

| `movement` | `demography` | `replicate` | `step` | `rho`  | `capy` |
| ---------- | ------------ | ----------- | ------ | ------ | ------ |
| one_sided  | constant     | 0           | 0      | 0.2500 | 0.9459 |
| one_sided  | constant     | 0           | 1      | 0.2500 | 0.9378 |

The displayed Capy score falls between steps zero and one of replicate zero even though its
first-group share `rho` remains 0.25. Tracking such a history requires all four identity fields:
`movement`, `demography`, `replicate`, and `step`. Alongside `capy`, each observation retains
`dissimilarity`, `entropy_index`, `moran_with_self`, and `moran_row_standardized`, plus
`demographic_horizon = 4000` and any additional source columns.

#### Pointwise summaries: `stochastic_trace_summary.parquet`

| `movement` | `demography` | `step` | `quantile` | `capy` |
| ---------- | ------------ | ------ | ---------- | ------ |
| one_sided  | constant     | 0      | 0.1000     | 0.9459 |
| one_sided  | constant     | 0      | 0.5000     | 0.9459 |

At step zero, the lower-band and median Capy values coincide in this example. They occupy separate
rows because `quantile` is part of the summary’s identity, alongside movement, demography, and
step. Values of 0.1, 0.5, and 0.9 denote the lower band, median, and upper band across included
replicates. All five score columns from the histories now hold their respective quantiles, ready
for plotting without further aggregation.

#### Replicate coverage: `source_replicate_coverage.parquet`

| `movement` | `demography` | `replicate` | `first_step` | `last_step` | `observation_count` | `included` |
| ---------- | ------------ | ----------- | ------------ | ----------- | ------------------- | ---------- |
| two_sided  | constant     | 0           | 0            | 800         | 801                 | True       |
| two_sided  | decline      | 22          | 0            | 518         | 519                 | False      |

The first replicate supplies all 801 observations from step zero through 800 and is included
whereas the second stops at 518 and is excluded. `first_step`, `last_step`, and
`observation_count` record that coverage, with `included` preserving the resulting decision. Match
these rows to score histories by movement, demography, and replicate. Excluded replicates remain
in this accounting table but contribute no saved score rows.

Included histories have 801 observations, one at every integer step from 0 through 800. These
files require finite scores and do not use shared-score reason columns. Coverage describes the
early interval, not the complete 4,000-step source.

To render the trajectories and their independent snapshot examples, plotting reads the trace
summary together with `stochastic_states.npz`. Inside the archive, each `<movement>_<demography>`
key holds integer population counts in `(6, 2, 20, 20)` snapshot, group, row, column order, with
group zero denoting the first population. The accompanying integer `snapshot_steps` array supplies
the observation times, which are not consecutive simulation steps. These independently simulated
examples have no replicate-ID join to the supplied histories.

## Iowa county configurations

The Iowa experiment compares random, isolated, clustered, and multicluster population arrangements
on an irregular geographic graph. It requires Iowa's joined 2020 county boundaries and populations
from the pipeline's
[geography-joining stage](national_pipeline/03_geography_population_joining.md).

```bash
uv run --locked python code/run_experiment.py iowa --samples-per-share 500 --share-count 100
uv run --locked python code/make_figures.py iowa
```

Preparation builds county adjacency once, then samples arrangements across the requested target
population shares. `--share-count` sets the number of targets per arrangement family, and
`--samples-per-share` sets the number of sampling attempts at each target. Whole-county
assignments can overshoot a target while an independent set can exhaust eligible counties before
reaching it. Scores therefore use the attained population shares.

The random baseline shuffles the counties and assigns whole counties to the first group until
their population reaches or exceeds the target, without imposing an adjacency constraint. This
samples prefixes of random county orders, not uniformly from all subsets at a given share.

The experiment uses the configured joined-geography input root but always selects 2020 Iowa
counties, regardless of the national selections. To use a configuration other than the default
`code/configs/replication.yaml`, supply its path through `--config`. Once preparation has saved
the county examples and edge pairs, rendering can display the scoring graph directly without
reconstructing adjacency.

Tables live under `results/experiments/iowa_configurations/`. Images are grouped by arrangement
under `figures/iowa_configurations/`, with a county graph and separate score plots for each.
Filenames begin with the plot type, followed by geography and arrangement, such as
`dualgraph_ia_county_clustered.png` and `capy_by_share_ia_county_clustered.png`. Moran plots
retain `moran_row_standardized` in their names.

Two combined panels compare random (denim), clustered (dark tangerine), and isolated (cadmium
green) arrangements: `capy_by_share_ia_county_comparison.png` and
`moran_row_standardized_by_share_ia_county_comparison.png`. Their points are shuffled with a fixed
drawing seed so no arrangement is consistently drawn on top. The separate
`county_arrangement_legend.png` identifies the colors for both panels. Multicluster results retain
their individual plots. If saved results lack the random baseline, rerun preparation before
rendering.

Individual score panels use the same arrangement colors, with purple heart for multicluster.
County maps show the first group in dark tangerine and the second in denim, connected by
slate-gray adjacency lines. These colors use GerryTools' LaTeX palette hex values. All Iowa
markers omit outlines so strokes do not inflate the small points in dense score panels.

### Saved Iowa format

#### Sampling results: `iowa_scores.parquet`

| `arrangement` | `sample` | `target_share` | `status` | `group_share` | `component_count` | `capy` |
| ------------- | -------- | -------------- | -------- | ------------- | ----------------- | ------ |
| isolated      | 0        | 0.0100         | ready    | 0.0164        | 3                 | 0.5306 |
| isolated      | 0        | 0.0149         | ready    | 0.0268        | 4                 | 0.5577 |

The same sample stream is evaluated at two target shares here, producing an attained `group_share`
above each requested `target_share`. A sampling attempt is identified by the combination of
`arrangement`, zero-based integer `sample`, and `target_share` while the omitted integer `seed`
records its random stream. Arrangement can be `random`, `isolated`, `clustered`, or
`multicluster`. The `status` distinguishes a `ready` result from `no_multicluster_sample`.

For a successful attempt, `component_count` counts the first-group components and the numeric
`capy` and `moran_row_standardized` fields score the attained arrangement. An unsuccessful
multicluster search leaves those fields and `group_share` null. This sampling outcome is separate
from an undefined metric, which raises during computation rather than being saved as a status or
per-metric reason.

#### Map examples: `iowa_examples.parquet`

| `arrangement` | `GEOID` | `TOTPOP` | `first_group` |
| ------------- | ------- | -------- | ------------- |
| isolated      | 19001   | 7496     | False         |
| isolated      | 19003   | 3704     | True          |

Each row is one county in the saved arrangement, identified by `arrangement` and text `GEOID`.
Here, county `19003` is assigned to the first group while county `19001` is not. The GeoParquet
file preserves the joined county columns and CRS, including `geometry` and integer population
counts `TOTPOP`, `WHITE`, `BLACK`, and `POC`, and adds text `arrangement` and Boolean
`first_group`. A true flag assigns that county's entire population to the synthetic first group.
These target-0.3 examples are sampled separately and have no `sample` join to the score table.
Inherited columns follow the
[joined-geography format](national_pipeline/03_geography_population_joining.md#read-the-outputs).

#### County adjacency: `iowa_edges.parquet`

| `source` | `target` |
| -------- | -------- |
| 19001    | 19003    |
| 19001    | 19029    |

Each row connects two counties in the graph. `iowa_edges.parquet` contains text `source` and
`target` county IDs, one lexically ordered pair per undirected edge. Both refer to `GEOID` in each
arrangement's example map. The renderer reads all three files and uses the saved edges for
adjacency.

## Neighborhood change

The `dispersion` workflow follows tract populations around selected neighborhood cores. It uses
the 2020 maximum-city definitions and requires completed tract inputs for 1980, 1990, 2000, 2010,
and 2020, as specified in the maximum-city configuration.

```bash
uv run --locked python code/run_experiment.py dispersion --config code/configs/max_city.yaml
uv run --locked python code/make_figures.py dispersion
```

City and neighborhood definitions in
[`observed_dispersion.py`](../code/experiments/neighborhood_change/observed_dispersion.py) specify
each core's component rank and reference tract. Before assigning a neighborhood name, preparation
checks that the ranked core contains its reference tract. This prevents a changed ranking from
silently relabeling a neighborhood. Saved core memberships, maps, and scores retain the accounting
needed to interpret the selected regions.

Preparation saves scores and tract memberships for every buffer from zero through ten graph steps.
`--buffer-steps` chooses the buffer used for saved maps and displayed score traces, defaulting to
three. The results live under `results/experiments/neighborhood_change/`.

Every neighborhood gets radial views while Chicago also gets choropleths and score traces. Each
neighborhood's plots share a folder beneath `figures/neighborhood_change/`, with shared colorbars
at that root. Map filenames begin with their type, for example `choro_1980_black_share.png` or
`radial_1980_black_share.png`.

### Saved neighborhood format

All four files share text `cluster`, such as `chicago_south_side`. Year and buffer coordinates are
integer `year` (Census year) and `buffer_steps` (zero through ten graph hops).

#### Buffered scores: `cluster_scores.parquet`

| `cluster`          | `year` | `buffer_steps` | `black_population` | `unit_count` | `mean_black_distance` | `capy` |
| ------------------ | ------ | -------------- | ------------------ | ------------ | --------------------- | ------ |
| chicago_south_side | 1980   | 0              | 800034             | 261          | 5.7818                | 0.7717 |
| chicago_south_side | 1980   | 1              | 807812             | 312          | 5.8188                | 0.8416 |

Expanding the displayed South Side selection by one graph step increases both its tract count
(`unit_count`) and Black population (`black_population`). Each row summarizes one combination of
`cluster`, `year`, and `buffer_steps`, with `mean_black_distance` measuring the
Black-population-weighted mean distance to the center tract in graph hops. That tract’s ID is
saved in the omitted `medoid` column. The remaining fields hold `group_share` and shared scores,
using Black as the first group and regular `capy`.

#### Tract membership: `cluster_memberships.parquet`

| `cluster`          | `year` | `buffer_steps` | `geographic_id` |
| ------------------ | ------ | -------------- | --------------- |
| chicago_south_side | 1980   | 0              | G17003103303    |
| chicago_south_side | 1980   | 0              | G17003103304    |

Each row says that a whole tract belongs to this neighborhood/year/buffer selection. All four
columns identify a membership. Because a tract can appear under several buffers or years,
`geographic_id` alone does not identify a row in this table.

#### Plotting tracts: `cluster_maps.parquet`

| `cluster`          | `year` | `buffer_steps` | `GEOID`      | `black_share` | `radial_x` | `radial_y` | `is_medoid` |
| ------------------ | ------ | -------------- | ------------ | ------------- | ---------- | ---------- | ----------- |
| chicago_south_side | 1980   | 3              | G17003102817 | 0.3308        | -4.5114    | 15.3508    | False       |
| chicago_south_side | 1980   | 3              | G17003102818 | 0.2727        | -3.3595    | 14.6189    | False       |

The map table adds a tract-level view of the selected buffer. Within a cluster, year, and buffer,
`GEOID` identifies the tract whose population composition appears as `black_share = BLACK / (BLACK +
WHITE)`. Its position in the radial view comes from `radial_x` and `radial_y`, with `is_medoid`
marking the center tract. Geometry, population counts, and source attributes remain in the full file
alongside these plotting fields.

#### Fixed cores: `cluster_cores.parquet`

| `cluster`          |
| ------------------ |
| chicago_south_side |
| chicago_austin     |

Each named cluster is paired with a `geometry` column containing its dissolved 2020 core as a
Polygon or MultiPolygon, with interior holes filled. Those long coordinate sequences are omitted
from the preview. Because a core supplies the fixed reference for every decade, `cluster` alone
identifies its row and no year column is needed.

Both geographic files use GeoParquet in `ESRI:102003`, whose map coordinates are measured in
meters, and the maps retain whole tract shapes. Radial positions combine a graph-hop distance with
the direction of the tract’s projected centroid from the medoid, so their coordinates are not
distances in meters. Within each year, the medoid stays fixed across buffers even though it may
change between years. Distances follow paths through the full city graph while scores use the
selected subgraph.

To connect the plotting tables, match map `GEOID` to membership `geographic_id` within the same
cluster, year, and buffer, then attach scores using those three selection fields. Scores and
memberships cover all eleven buffers, but map geometry is saved only for the requested plotting
buffer. Inherited attributes follow the
[joined-geography format](national_pipeline/03_geography_population_joining.md#read-the-outputs),
with nulls where a source field is absent in another decade. The renderer reads these three tables
together, leaving the core geometry available for separate inspection.

## Paths and plot adjustments

Both commands accept several workflow names, execute them in the supplied order, and stop at the
first failure. Options apply to the selected workflows that use them, with one value per option
for the invocation. The CLI help lists defaults and accepted ranges.

`--data-directory` changes the result root for either command, and `--output-directory` changes
the figure root for rendering. Each command adds the workflow subfolders beneath that root.
Relative result, figure, and stochastic-source paths begin at the repository root whereas an
explicit relative `--config` filename begins at the shell's current directory. Reruns replace
matching outputs without deleting unrelated files. Since an interrupted write can leave incomplete
results, finish preparation before rendering.

Each experiment's plotting module controls its visual presentation. Adjust ticks, scales, and
annotations on its axes before the call to `save_plot()`, which saves and closes the figure. Some
modules provide drawing helpers that accept caller-owned `Axes` and leave them open for these
adjustments. Shared colors live near the top of
[`figure_style.py`](../code/plotting/figure_style.py). Keep experiment-specific display choices
with the corresponding plotting code.
