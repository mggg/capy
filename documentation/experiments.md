# Grid, diffusion, and geographic experiments

Use `code/run_experiment.py` to compute results and `code/make_figures.py` to render the saved
results. Both accept several workflow names in execution order. Computation never draws images,
and rendering reads saved tables and arrays without rebuilding graphs, fitting curves, or
recalculating scores. Each image is a separate 300 dpi PNG without titles or axis labels, with
legends and colorbars saved separately for LaTeX assembly.

## Grid arrangements and reference curves

```bash
uv run --locked python code/run_experiment.py grid-reference-scores grid-pop-share-arrangements grid-score-comparisons triangular
uv run --locked python code/make_figures.py grid-reference-scores grid-pop-share-arrangements grid-score-comparisons triangular
```

`grid-reference-scores` saves continuous-mass score curves for clustered, constant, isolated, and
checkerboard arrangements on a four-neighbor square lattice. Cluster curves are large-region
limits. Density alone does not determine spatial dissimilarity, information, or relative diversity
for the isolated arrangement, so those curves are absent. Gray shading marks lattice reference
regions rather than universal bounds for irregular graphs. Coincident curves retain their exact
values, distinguished by line styles.

`grid-pop-share-arrangements` saves nine grids from three population-share distributions and
three arrangements. `grid-score-comparisons`
adds six perturbations per combination, producing 54 share examples, plus sixty binary grids with
72 people of each group. The binary classes have 30–50, 120–145, or 210–235 unlike-neighbor edges.
All examples have population share 0.5, so their score points lie on that vertical line. The saved
score table carries explicit population distribution, arrangement, sample, and category fields. Its reference
scores are saved during preparation; changing a formula requires rerunning that step.

`triangular` computes the Reardon–O'Sullivan lattice examples and their observation windows.
Outputs live under `results/experiments/reardon_osullivan/` and
`figures/grid_configurations/reardon_osullivan/`. Other grid families use descriptive folders
under `results/experiments/grid_configurations/` and `figures/grid_configurations/`.

For score distributions from randomized binary arrangements:

```bash
uv run --locked python code/run_experiment.py grid-distributions --samples 10000 --seed 20260918
uv run --locked python code/make_figures.py grid-distributions
```

Each cell contains 100 people of one group, so these scores use regular Capy.
This retains the sampled score rows and representative grids. Histograms are drawn from those
saved samples; changing styles does not repeat the sampling.
Images in `figures/grid_configurations/distributions/` identify the clustering class and plot type,
for example `grid_low_clustering.png` and `low_clustering_capy_histogram.png`.

## Expanding-support diffusion

```bash
uv run --locked python code/run_experiment.py expanding-support
uv run --locked python code/make_figures.py expanding-support
```

`expanding-support` uses 20×20 grids with a centered rectangle, a rook-expanding core, or a thick
cross. Each begins with a pure first-group region and zero first-group share outside it, then
spreads mass uniformly over the growing support.

The rectangle begins at 10×10 and adds alternating horizontal and vertical bands. The core begins
at 5×5 and expands by rook steps. The thick cross begins with 99 occupied cells and uses the same
rook-distance rule. Each shape has constant, growth, and decline variants. Rectangle and cross
growth end at share 0.4 and decline at 0.1; the smaller core ends at 0.1 and 0.025. Each cell has
total mass one. Overall first-group shares change linearly with step for the rectangle and core,
and with occupied area for the cross. Shares within occupied cells equal the overall share
divided by the occupied fraction of the grid.

Dissimilarity, entropy, and Capy traces overlay the demographic variants. The Moran comparison
uses closed-neighborhood and row-standardized weights. Within a shape, scaling all cell shares by
a common multiplier leaves Moran unchanged; the final uniform grid has undefined Moran and remains
a gap. Each shape has a folder under
`results/experiments/synthetic_diffusion/expanding_support/`, containing `states.npz` and
`expanding_support_scores.parquet`. The corresponding folder under
`figures/synthetic_diffusion/expanding_support/` contains its snapshots, score plots, legends,
and colorbar. Shape folders use names such as `centered_rectangle` and `rook_expanding_core`.

## Stochastic diffusion

```bash
uv run --locked python code/run_experiment.py stochastic \
    --moon-source-directory /path/to/moon-capy/code/capy_deck_replication
uv run --locked python code/make_figures.py stochastic
```

Preparation reads the two long-run score CSVs under the source directory's
`scripts/synthetic/stochastic_data/`. It saves complete early replicate histories, their medians
and pointwise 10th–90th percentile bands, and independent seeded snapshot trajectories. Rendering
reads these saved results without consulting the source CSVs or aggregating the replicates again.
The supplied replicate scores are reused, not recomputed with the current metric functions.

Every cell initially contains 1,000 people. The central 10×10 square is entirely the first group;
other cells are entirely the second. At each step, a person moves to a uniformly chosen rook
neighbor with probability 0.2. One-sided diffusion moves only the first population; two-sided
moves both. First-group births or deaths follow movement. Growth doubles expected first-group
population over 4,000 steps, while decline reduces it to one third. The plotted interval ends at
step 800, using those same rates.

Snapshots at steps 0, 25, 100, 250, 500, and 800 are independent examples rather than replicate
medians. The NPZ stores these step coordinates alongside the population arrays. Separate images
show group share and first-group counts; count colors saturate at 1,000 to keep a common scale.
The one-sided cache has 25 complete early replicates per variant. Two-sided constant and growth
have 23 each, and decline has 22. A decline replicate ending at step 518 is excluded throughout;
`source_replicate_coverage.parquet` records that decision. Results live under
`results/experiments/synthetic_diffusion/stochastic/one_sided/` and `two_sided/`, each containing
its score tables, replicate coverage, and snapshot arrays. Figures use the same movement
subfolders under `figures/synthetic_diffusion/stochastic/`, with legends and colorbars beside
the plots.

## Paths and plot adjustments

Grid-score comparison images are grouped into `grids/` and `scores/` under
`figures/grid_configurations/grid_score_comparisons/`. Legends live beside the score plots.

`--data-directory` changes the result root for either command; `--output-directory` changes the
figure root for rendering. Relative paths begin at the repository root. Reruns replace matching
outputs without deleting unrelated files. Complete computation before plotting, and rerun
preparation after an interrupted write.

Drawing functions accept caller-owned `Axes` and leave them open. Make tick, scale, and annotation
changes after drawing and before the batch function calls `save_plot()`. Shared colors live near
the top of `code/plotting/figure_style.py`; family-specific display choices stay with their plots.

Binary grid examples use exact Capy because each node represents one person.
Fractional population masses use regular Capy, including when masses sum to one per node.
