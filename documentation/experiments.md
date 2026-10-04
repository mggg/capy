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
