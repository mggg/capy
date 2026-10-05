# Figures

Use this folder to find figure components for the national analyses and controlled experiments.
The directory guide links each comparison to its methods, input requirements, and saved-data
examples. Plots, legends, and colorbars are supplied as separate 300 dpi PNGs so they can be
assembled in LaTeX or TikZ, where titles and axis labels are added.

## Find a figure

| Directory                                                                        | What the figures examine                                                                                            | Guide                                                                                            |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| [national/history/](national/history/)                                           | How segregation scores change over Census years for fixed area cohorts.                                             | [Score histories](../documentation/figures.md#national-score-histories)                          |
| [national/population_composition/](national/population_composition/)             | How scores relate to Black population share, with fitted relationships by year.                                     | [Population composition](../documentation/figures.md#population-composition)                     |
| [national/score_ranks/](national/score_ranks/)                                   | How different metrics rank the same population-selected areas.                                                      | [Score ranks](../documentation/figures.md#score-ranks)                                           |
| [national/capy_weights/](national/capy_weights/)                                 | How area rankings change with Capy's neighbor weight.                                                               | [Neighbor weights](../documentation/figures.md#capy-neighbor-weights)                            |
| [national/entropy_by_geography/](national/entropy_by_geography/)                 | How entropy histories differ across tracts, block groups, and blocks.                                               | [Entropy by level](../documentation/figures.md#entropy-by-geographic-level)                      |
| [national/grid_vs_national_scores/](national/grid_vs_national_scores/)           | How observed tract scores compare with idealized square-lattice curves.                                             | [Grid versus national scores](../documentation/figures.md#grid-versus-national-scores)           |
| [grid_configurations/](grid_configurations/)                                     | How population arrangement affects scores on square grids, including reference curves and randomized distributions. | [Grid experiments](../documentation/experiments.md#grid-arrangements-and-reference-curves)       |
| [reardon_osullivan/](reardon_osullivan/)                                         | Published triangular-lattice population arrangements.                                                               | [Reardon–O’Sullivan examples](../documentation/experiments.md#reardonosullivan-lattice-examples) |
| [synthetic_diffusion/expanding_support/](synthetic_diffusion/expanding_support/) | How spatial spreading and population growth or decline affect scores.                                               | [Expanding support](../documentation/experiments.md#expanding-support-diffusion)                 |
| [synthetic_diffusion/stochastic/](synthetic_diffusion/stochastic/)               | How scores and population patterns evolve under one-sided or two-sided stochastic movement.                         | [Stochastic diffusion](../documentation/experiments.md#stochastic-diffusion)                     |
| [iowa_configurations/](iowa_configurations/)                                     | How isolated, clustered, and multicluster assignments behave on Iowa's county graph.                                | [Iowa configurations](../documentation/experiments.md#iowa-county-configurations)                |
| [neighborhood_change/](neighborhood_change/)                                     | How tract populations and scores change around fixed neighborhood cores in Chicago and Philadelphia.                | [Neighborhood change](../documentation/experiments.md#neighborhood-change)                       |

## Read the names

A national path such as
`national/history/WB_CBSA20_block_group_histories/BLOCK_GROUP_capy_histories.png` identifies
White–Black Capy histories using block-group nodes inside CBSAs defined in 2020. The `20` in
`CBSA20` is the definition vintage, not the year of every plotted observation.

Reading a national name from left to right, `WB` or `WPOC` identifies the White–Black or White–POC
comparison, followed by a study-area label such as `CBSA20`, `MAX_CITY20`, `MAX_COUNTY20`, or
`COUNTY20`. In `WB_CBSA20_2020_tract`, the four-digit year specifies the Census observation and
`tract` gives the graph-node resolution. Other resolution labels include `block_group` and
`block`. A metric suffix then identifies the formula, including any consequential weighting
choice, as in `moran_row_standardized`. Further examples appear in the
[national guide](../documentation/figures.md#figure-components-and-saved-tables).

Experiment filenames reflect the scenarios being studied. In expanding-support diffusion,
`synthetic_diffusion/expanding_support/thick_cross/02_dec_thick_cross_diffusion.png` names the
step-two snapshot of a declining first-group population arranged as a thick cross. Its `dec` label
distinguishes decline from the constant (`const`) and growth (`inc`) variants. Iowa’s
`clustered/dualgraph_ia_county_clustered.png` instead names a county-graph illustration and its
population arrangement, so interpret these labels within their respective workflows.

## Regenerate components

Run commands from the repository root after
[setting up the environment](../README.md#set-up-the-environment). Preparation computes and saves
the plotting inputs, which rendering then reads to draw the images. For a small grid example that
needs no national pipeline inputs:

```bash
uv run --locked python code/run_experiment.py grid-pop-share-arrangements
uv run --locked python code/make_figures.py grid-pop-share-arrangements
```

This saves tables and arrays under
`results/experiments/grid_configurations/grid_pop_share_arrangements/` and images under
`figures/grid_configurations/grid_pop_share_arrangements/`.

For national histories, first complete the pipeline's metric outputs and study-area definitions,
then use the same configuration for preparation and rendering:

```bash
uv run --locked python code/run_experiment.py national --config code/configs/replication.yaml
uv run --locked python code/make_figures.py national --config code/configs/replication.yaml
```

After changing only colors, line styles, or other presentation settings, rerun `make_figures.py`.
Changes to inputs or analysis selections require preparing results again, including any affected
upstream pipeline stages. Other experiments have their own prerequisites in the linked guides.

To process several workflows, supply their names in one invocation. You can redirect saved results
with `--data-directory` and rendered images with `--output-directory`; each command adds its
workflow subfolders beneath the chosen root. Relative paths start at the repository root, and
rerunning a command replaces matching outputs. The available workflows and options are listed in
`--help`.

## Assemble a figure

Choose legends and colorbars that explain the panels you are assembling. An expanding-support
shape folder, for example, supplies `demography_legend.png` for the demographic score traces,
`moran_conventions_legend.png` for the Moran comparison, and `share_colorbar.png` for the
population snapshots. National history folders likewise keep their highlight and individual-area
legends beside the plots. Where several selections share a component, the workflow guide points to
its location in a parent directory.

During LaTeX or TikZ assembly, add titles, axis labels, panel letters, and captions around the
saved plots, retaining their numeric ticks where present. Size the components with their text and
symbols in mind: because legends and colorbars have their own image bounds, matching PNG widths
may produce mismatched lettering. Components from the same selection and rendering run should stay
together to preserve agreement between colors and labels.

## Find the underlying numbers

National plotting inputs live under `results/national/processed_data/`, grouped by analysis and
study-area selection. Finished publication tables live under `results/national/tables/`.
Experiment tables and arrays live under `results/experiments/`, grouped by experiment family.

For the numbers behind a plot, start with the two-row examples in the
[national guide](../documentation/figures.md#reading-the-saved-tables) or
[experiment guide](../documentation/experiments.md#saved-table-conventions). The explanations show
how to read the saved columns, population denominators, missing values, and joins. Alongside those
examples, the workflow sections describe the cohort and reference-curve choices needed to
interpret the comparisons.
