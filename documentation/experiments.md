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

- [Grid arrangements and reference curves](#grid-arrangements-and-reference-curves)
- [Expanding-support diffusion](#expanding-support-diffusion)
- [Stochastic diffusion](#stochastic-diffusion)
- [Iowa county configurations](#iowa-county-configurations)
- [Neighborhood change](#neighborhood-change)
- [Paths and plot adjustments](#paths-and-plot-adjustments)

## Grid arrangements and reference curves

The grid experiments compare scores for controlled spatial arrangements. The first three workflows
below use square lattices while `triangular` produces the Reardon–O'Sullivan lattice examples and
their observation windows.

```bash
uv run --locked python code/run_experiment.py \
    grid-reference-scores grid-pop-share-arrangements grid-score-comparisons triangular
uv run --locked python code/make_figures.py \
    grid-reference-scores grid-pop-share-arrangements grid-score-comparisons triangular
```

`grid-reference-scores` computes score curves for clustered, constant, isolated, and checkerboard
arrangements of continuous population mass on a square lattice with four neighbors per interior
cell. The clustered curves describe large-region limits. For isolated arrangements, density alone
cannot determine spatial dissimilarity, information, or relative diversity, so those curves are
omitted. Gray shading identifies lattice reference regions; it does not establish universal bounds
for irregular graphs. Where curves coincide, their exact values are preserved and line styles
distinguish them.

`grid-pop-share-arrangements` combines three population-share distributions with three spatial
arrangements to produce nine grids. `grid-score-comparisons` adds six perturbations per
combination, producing 54 share examples, alongside sixty binary grids with 72 people of each
group. The binary classes have 30–50, 120–145, or 210–235 unlike-neighbor edges. Every example has
overall population share 0.5, so its point lies on that vertical line in a score-versus-share
plot. The saved score table identifies the population distribution, arrangement, sample, and
category. Preparation also saves the reference scores, which remain fixed until the next
preparation run.

These square-grid workflows save results under `results/experiments/grid_configurations/` and
images under `figures/grid_configurations/`, in a folder named for each experiment. The score
comparison images are further divided into `grids/` and `scores/`, with legends beside the score
plots. The triangular examples use `results/experiments/reardon_osullivan/` and
`figures/grid_configurations/reardon_osullivan/`.

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
the rectangle and cross, growth ends at overall first-group share 0.4 and decline at 0.1; the
smaller core ends at 0.1 and 0.025, respectively. Overall shares change linearly with step for the
rectangle and core, and with occupied area for the cross. Within the occupied region, each cell's
first-group share equals the overall share divided by the occupied fraction of the grid.

The dissimilarity, entropy, and Capy plots overlay the three demographic variants. A separate
Moran comparison uses closed-neighborhood and row-standardized weights. Within a shape, scaling
all cell shares by a common multiplier leaves Moran unchanged. Moran is undefined on the final
uniform grid, so that endpoint remains a gap in the plot.

Each shape has a folder under `results/experiments/synthetic_diffusion/expanding_support/`,
containing `states.npz` and `expanding_support_scores.parquet`. The corresponding folder under
`figures/synthetic_diffusion/expanding_support/` contains snapshots, score plots, legends, and a
colorbar. Shape folders use names such as `centered_rectangle` and `rook_expanding_core`.

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
images show group share and first-group counts; count colors saturate at 1,000 to keep a common
scale.

The supplied one-sided results have 25 complete early replicates per variant. Two-sided constant
and growth have 23 each, and decline has 22. A decline replicate ending at step 518 is excluded
throughout the interval, with the exclusion recorded in `source_replicate_coverage.parquet`.
Results live under `results/experiments/synthetic_diffusion/stochastic/one_sided/` and
`two_sided/`, each containing score tables, replicate coverage, and snapshot arrays. Figures use
the same movement subfolders under `figures/synthetic_diffusion/stochastic/`, with legends and
colorbars beside the plots.

## Iowa county configurations

The Iowa experiment compares isolated, clustered, and multicluster population arrangements on an
irregular geographic graph. It requires Iowa's joined 2020 county boundaries and populations from
the pipeline's [geography-joining stage](national_pipeline/03_geography_population_joining.md).

```bash
uv run --locked python code/run_experiment.py iowa --samples-per-share 500 --share-count 100
uv run --locked python code/make_figures.py iowa
```

Preparation builds county adjacency once, then samples arrangements across the requested target
population shares. `--share-count` sets the number of targets per arrangement family, and
`--samples-per-share` sets the number of sampling attempts at each target. Whole-county
assignments can overshoot a target while an independent set can exhaust eligible counties before
reaching it. Scores therefore use the attained population shares.

The configuration supplies the joined-geography input root; the experiment always uses 2020 Iowa
counties regardless of the configured national selections. By default it reads
`code/configs/replication.yaml`; `--config` selects an alternative configuration. The saved edge
pairs and county examples preserve the graph used for scoring, so rendering can display it without
reconstructing adjacency.

Tables live under `results/experiments/iowa_configurations/`. Images are grouped by arrangement
under `figures/iowa_configurations/`, with a county graph and separate score plots for each.
Filenames begin with the plot type, followed by geography and arrangement, such as
`dualgraph_ia_county_clustered.png` and `capy_by_share_ia_county_clustered.png`. Moran plots
retain `moran_row_standardized` in their names.

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
`--buffer-steps` chooses the buffer used for saved maps and displayed score traces; its default is
three. The results live under `results/experiments/neighborhood_change/`.

Every neighborhood gets radial views while Chicago also gets choropleths and score traces. Each
neighborhood's plots share a folder beneath `figures/neighborhood_change/`, with shared colorbars
at that root. Map filenames begin with their type, for example `choro_1980_black_share.png` or
`radial_1980_black_share.png`.

## Paths and plot adjustments

Both commands accept several workflow names, execute them in the supplied order, and stop at the
first failure. Options apply to the selected workflows that use them, with one value per option
for the invocation. The CLI help lists defaults and accepted ranges.

`--data-directory` changes the result root for either command, and `--output-directory` changes
the figure root for rendering. Each command adds the workflow subfolders beneath that root.
Relative result, figure, and stochastic-source paths begin at the repository root whereas an
explicit relative `--config` filename begins at the shell's current directory. Reruns replace
matching outputs without deleting unrelated files. An interrupted write can leave incomplete
results; rendering depends on a completed preparation run.

Each experiment's plotting module controls its visual presentation. Drawing functions accept
caller-owned `Axes` and leave them open, allowing tick, scale, and annotation changes after
drawing and before `save_plot()`. Shared colors live near the top of
[`figure_style.py`](../code/plotting/figure_style.py); display choices specific to an experiment
stay with its plotting code.
