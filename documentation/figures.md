# National figures and tables

The national figure sets describe score histories, population relationships, and comparisons
between segregation metrics. They draw on completed pipeline results and include publication
tables. Each workflow first prepares the observations needed for its analysis, then renders
figures from those saved results. The ranked population table needs only the preparation step. The
[experiment guide](experiments.md) describes the controlled grid, diffusion, and geographic
experiments.

Figures are saved as separate 300 dpi PNG components for LaTeX assembly. Numeric ticks remain
while titles and axis labels are added in LaTeX. Legends are saved separately with tight bounds.

## Contents

- [National score histories](#national-score-histories)
- [Figure components and saved tables](#figure-components-and-saved-tables)
- [Selections and interpretation](#selections-and-interpretation)
- [Two-node historical graphs](#two-node-historical-graphs)
- [History plot styling](#history-plot-styling)
- [Population composition](#population-composition)
- [Score ranks](#score-ranks)
- [Ranked population table](#ranked-population-table)
- [Capy neighbor weights](#capy-neighbor-weights)
- [Entropy by geographic level](#entropy-by-geographic-level)
- [Grid versus national scores](#grid-versus-national-scores)

## National score histories

The `national` figure set shows segregation-score histories for the configured study areas. Its
inputs come from the completed
[metric computation stage](national_pipeline/06_metric_computation.md#run-the-stage). The command
examples below assume the repository root as the working directory.

```bash
uv run --locked python code/run_experiment.py national --config code/configs/replication.yaml
uv run --locked python code/make_figures.py national --config code/configs/replication.yaml
```

The first command selects metros and score histories from the completed pipeline outputs and saves
them as tables. The second draws images from those saved tables only, so style changes can be
redrawn without repeating the selection. Changes to graph inputs or scores require rerunning the
affected pipeline stages and then both commands.

The configuration selects the study-area type, definition vintage, Census years, geography levels,
population comparisons, and metrics. Histories are available for White–Black and White–POC
comparisons at tract, block-group, and block levels. Only configured selections are prepared, so a
tract-only or later-decade run does not require other levels or 1980 data. Because the source
collection has no 1980 block or block-group boundaries, those histories begin with the first
supported configured year.

Preparation reads the study-area definitions, selected metric tables, and matching graph summary,
such as `CBSA20_graph_summary.parquet`. Each selected graph must have a row for every requested
history score and population comparison, including an explicit undefined result where appropriate.
Missing files or score rows stop preparation. Preparation and plotting share the same
configuration, and plotting uses the saved cohorts. A different selection takes effect only after
new tables have been prepared.

The supported combinations and scores are defined by `HISTORY_SELECTIONS` and `HISTORY_METRICS` in
[`prepare_national_results.py`](../code/national_figures/prepare_national_results.py). These lists
limit the available histories while the configuration chooses which ones to include in a run.

Each command accepts one or more workflow names, runs them in the supplied order, and stops if one
fails. Shared options apply to the whole invocation. Tables default to `results/` and images to
`figures/`; `--data-directory` changes the table root for both commands, and `--output-directory`
changes the figure root for `make_figures.py`. Relative result and figure paths start at the
repository root. An explicit relative `--config` filename starts at the shell's current directory;
without one, both commands use `code/configs/replication.yaml` in the repository. Reruns replace
matching outputs.

For `national`, preparation computes and validates all four history tables before saving any of
them. A selection or cohort-check failure therefore leaves existing tables unchanged. Writes are
sequential, however, so a failure during saving can leave an incomplete set that requires another
preparation run before plotting.

## Figure components and saved tables

National images are grouped by experiment, with each selection's images and legends kept together.
Their plotting inputs live under `results/national/processed_data/`, grouped by experiment.
Finished tables, including ranked population tables and rank-correlation summaries, live under
`results/national/tables/` in both CSV and Parquet formats.

National output names use `WB` for White–Black and `WPOC` for White–POC, followed by an uppercase
study-area type and two-digit definition year: `CBSA20`, `MAX_CITY20`, `MAX_COUNTY20`, or
`COUNTY20`. Census years remain four digits. Geography names are singular: `tract`, `block_group`,
`block`, and `county`. Prepared inputs usually live in a study-area folder such as `CBSA20`.
Entropy inputs also identify their White–Black comparison in the folder name:
`results/national/processed_data/entropy_by_geography/WB_CBSA20/`. These path labels do not change
identifiers inside tables or the pipeline's input paths.

History images are saved under `figures/national/history/`, and their prepared tables under
`results/national/processed_data/history/<study_area_label>/`.

Each image combines individual area histories, their arithmetic mean, and colored top-ten
histories. Names such as `TRACT_capy_histories.png` and `BLOCK_GROUP_capy_histories.png` identify
the geography and score. Both legends, `top_10_legend.png` and `individual_metro_legend.png`, live
alongside the images. The x-axis covers the configured years, with a gray band from 1980 to 1990
for blocks and block groups when 1980 is requested.

The history metrics include Capy, aspatial Capy, dissimilarity, entropy, relative diversity, their
three spatial segregation variants, and both row-standardized and self-inclusive Moran's I. Only
metrics selected by `metric_names` are prepared. Each metric keeps its own complete cohort, using
the population cutoff and historical exclusions described below.

The prepared tables are `national_score_rows.parquet` (selected scores for eligible areas),
`eligible_areas.parquet`, `top_10_metros.parquet`, and `trajectory_rows.parquet` (the complete
histories that the panels draw).

## Selections and interpretation

Eligible study areas have a definition population strictly above 100,000 in the configured
vintage. The top ten are the ten most populous eligible areas, with geographic ID breaking ties,
chosen before any score-based filtering. Each metric's histories then keep the eligible areas with
a finite score in every supported configured year, subject to the historical exclusion below, so
each metric has its own fixed cohort. A top-ten area without a complete history would appear in
the legend without a line. Pale lines show individual areas, and the blue mean gives each area
equal weight.

Capy includes self-pair terms and uses neighbor weight 1. It is read from the pipeline metric
tables alongside the other scores, which use graphs filtered to positive White-plus-Black
population; see
[population filtering](national_pipeline/05_graph_construction.md#population-filtering-and-adjacency).

## Two-node historical graphs

When the configuration uses 2020 CBSA definitions and includes 1980, White–Black tract histories
exclude the following five CBSAs from every plotted year and all selected history scores. The
exclusion applies to both individual trajectories and the mean across metros. It leaves the
pipeline graphs and metric tables intact. Later-only histories and other study-area definitions do
not apply this exclusion.

| CBSA code | Metro                           |
| --------- | ------------------------------- |
| 25940     | Hilton Head Island–Bluffton, SC |
| 29420     | Lake Havasu City–Kingman, AZ    |
| 35100     | New Bern, NC                    |
| 39150     | Prescott Valley–Prescott, AZ    |
| 39460     | Punta Gorda, FL                 |

Each metro's 1980 graph consists of two block-numbering areas (BNAs) from NHGIS's
`US_bna_1980.shp` layer, joined by one ordinary adjacency edge. Neither population filtering nor
artificial connections produced these two-node graphs. With unequal population shares, centering
gives deviations $a$ and $-a$, and row-standardized Moran's I is necessarily
$2a(-a)/(a^2+(-a)^2)=-1$. That value reflects the two-node representation rather than
distinguishing the strength of demographic clustering among these metros.

We omit their complete histories because this spatial resolution gives an uninformative 1980 Moran
comparison. Applying the same exclusion to all history scores keeps the decision consistent across
the image set while removing every year preserves each metric's fixed cohort. Other negative Moran
scores remain eligible. This is a specific historical-coverage exclusion, not a general cutoff on
score values.

## History plot styling

History styling is defined in
[`plot_national_results.py`](../code/national_figures/plot_national_results.py). Its
`plot_score_history()` function controls line and mean styling, ticks, grid lines, and shading.
These settings affect rendering without changing the prepared observations.

Year labels appear on every history image, including entropy histories. `HISTORY_X_TICK_LABELS`
overrides individual labels, for example `{1980: "'80", 1990: "'90"}`; unspecified years retain
their full labels. An empty string hides an individual label while `HISTORY_SHOW_X_TICK_LABELS =
False` hides them all without removing the ticks or grid lines. The function draws on the supplied
axes and leaves them open for adjustments in `plot_national_figures()` before `save_plot()`.
Separate legends use the plotted lines' styles, including their markers and widths.

## Population composition

The population-composition figures show the relationship between Black population share and each
primary segregation score.

```bash
uv run --locked python code/run_experiment.py population-composition --config code/configs/replication.yaml
uv run --locked python code/make_figures.py population-composition --config code/configs/replication.yaml
```

This set uses White–Black tract scores for areas with definition population above 100,000 and more
than 100,000 retained total residents in every configured decade. The population threshold
includes all groups while the horizontal coordinate is Black/(White+Black). Each score keeps a
complete history cohort. Preparation saves both those observations and the fitted linear
relationships, allowing plotting to read them without fitting again.

Images live under `figures/national/population_composition/`. Year colors are controlled by
`YEAR_BASE_COLOR` in [`figure_style.py`](../code/plotting/figure_style.py). The default is a fixed
dark-to-light blue palette; `AMBER`, `PURPLE_HEART`, or another color produces shades of that
color.

## Score ranks

The `score-ranks` figures compare how the primary metrics order study areas, with a separate
sample for each configured year, geography level, and population comparison.

```bash
uv run --locked python code/run_experiment.py score-ranks --config code/configs/replication.yaml
uv run --locked python code/make_figures.py score-ranks --config code/configs/replication.yaml
```

Each selection has its own sample of up to one hundred areas, chosen by retained population among
areas with definition population above 100,000 and finite values for every selected primary
metric. The comparison requires at least two of the primary metrics: Capy, dissimilarity, and
row-standardized Moran's I. Omitted metrics neither restrict the sample nor produce images.

Within each sample, scores receive ascending ranks, with average ranks for ties. Preparation stops
if selected score records are missing. The saved ranks and correlations identify their Census
year, geography level, and population comparison, so results from different samples remain
distinguishable. Rank rows are saved under
`results/national/processed_data/score_ranks/<study_area_label>/`, and correlation summaries under
`results/national/tables/score_ranks/<study_area_label>/`.

Images live under `figures/national/score_ranks/`. Names begin with their year and level, for
example `2020_tract_dissimilarity_vs_capy.png`.

## Ranked population table

The ranked population table lists the areas with the highest Capy scores alongside their
populations and supplementary metrics. The `ranked-population-table` workflow produces finished
tables without a corresponding figure set.

```bash
uv run --locked python code/run_experiment.py ranked-population-table --config code/configs/replication.yaml
```

For each configured year, geographic level, and population comparison, preparation saves up to one
hundred areas with the highest finite Capy scores. Definition population must exceed 100,000, and
score ties are broken by area ID. Capy is required; other selected primary metrics appear as
supplementary columns. Undefined supplementary scores remain null.

Each row includes its selection identifiers, rank, area identity, selected scores, retained
population in millions, and the second group's share of total retained population. This share
includes groups outside the White–Black comparison in its denominator. CSV and Parquet copies are
saved under `results/national/tables/ranked_population_table/<study_area_label>/`.

## Capy neighbor weights

The `capy-weights` analysis compares area rankings at neighbor weights zero, one, and the
infinite-weight limit of quadratic Capy. It reads tract graphs directly, so completed graph
archives are required:

```bash
uv run --locked python code/run_experiment.py capy-weights --config code/configs/replication.yaml
uv run --locked python code/make_figures.py capy-weights --config code/configs/replication.yaml
```

The configuration must select CBSAs and include tracts; other geography levels are ignored. For
each configured year, preparation independently selects up to one hundred ready tract graphs by
retained total population and calculates scores at all three weights for every configured
population comparison. Missing ready graphs or undefined scores stop preparation, preserving the
selected sample. Plotting also restricts saved rows to tracts.

In the infinite-weight limit, a group with no neighbor interactions retains its within-unit
fraction.

Plotting reads the saved ranks from
`results/national/processed_data/capy_weights/<study_area_label>/`. Each year and population
comparison gets a descriptively named tract PNG directly in `figures/national/capy_weights/`, for
example `WB_CBSA20_2020_tract_capy_neighbor_weights.png`. All selections share
`neighbor_weights_legend.png` in that directory.

## Entropy by geographic level

The `entropy-by-geography` figures compare White–Black entropy histories across the selected
geographic resolutions.

```bash
uv run --locked python code/run_experiment.py entropy-by-geography --config code/configs/replication.yaml
uv run --locked python code/make_figures.py entropy-by-geography --config code/configs/replication.yaml
```

Each level has a separate cohort of areas with definition population above 100,000 and complete
histories from its first supported configured year. The highlighted top ten are the most populous
eligible areas in the study-area definitions, selected before checking their histories. Each must
have a complete history at every selected level. Preparation saves their identities alongside the
cohorts. Images and legends live together in `figures/national/entropy_by_geography/`.

## Grid versus national scores

The `grid-vs-national-scores` workflow places observed 2020 tract scores alongside square-lattice
reference curves:

```bash
uv run --locked python code/run_experiment.py grid-vs-national-scores --config code/configs/replication.yaml
uv run --locked python code/make_figures.py grid-vs-national-scores --config code/configs/replication.yaml
```

The configuration must include 2020 tracts and select either CBSAs or maximum cities. Preparation
reads the selected comparisons and metrics with their retained population accounting, applying no
population cutoff. Highlights use a fixed list of the ten largest 2020 metros.

Each metric gets a separate image with a matching legend. The reference curves describe a regular
square lattice and should not be read as universal bounds for irregular graphs. Both observations
and reference curves use regular Capy.

Prepared tables live under `results/national/processed_data/grid_vs_national_scores/CBSA20/`.
Images live under `figures/national/grid_vs_national_scores/`, with names such as
`TRACT_grid_v_nat_capy_by_share.png` and `TRACT_grid_v_nat_top_10_capy_by_share.png`. The samples
share `top_10_legend.png` and `reference_legend.png`.
