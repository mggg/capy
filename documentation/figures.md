# National image sets

Use these commands after the national pipeline has computed its metric tables to draw the national
figures. Each image is a separate 300 dpi PNG without a title or axis labels, ready for LaTeX
assembly. Numeric ticks remain, and legends are separate components with tight bounds.

## Contents

- [Run the available sets](#run-the-available-sets)
- [Find the components](#find-the-components)
- [Selections and interpretation](#selections-and-interpretation)
- [Two-node historical graphs](#two-node-historical-graphs)

## Run the available sets

From the repository root, prepare the figure tables and then draw them:

```bash
uv run --locked python code/run_experiment.py national --config code/configs/replication.yaml
uv run --locked python code/make_figures.py national --config code/configs/replication.yaml
```

The first command selects metros and score histories from the completed pipeline outputs and saves
them as tables. The second draws images from those saved tables only, so style changes can be
redrawn without repeating the selection. Changes to graph inputs or scores require rerunning the
affected pipeline stages and then both commands.

Preparation uses the configured study-area type, vintage, years, geography levels, population
comparisons, and metrics. `HISTORY_SELECTIONS` in
`code/national_figures/prepare_national_results.py` lists the image sets, and `PRIMARY_METRICS`
lists their scores; only entries selected by the configuration are prepared. The current sets are
White–Black histories for tracts, block groups, and blocks, and White–POC tract histories, using
Capy, row-standardized Moran's I, and dissimilarity. A tract-only or later-decade run does not
require the other levels or 1980 data.

It reads study-area definitions, the image sets' metric tables, and the matching graph summary
(for example, `CBSA20_graph_summary.parquet`), so the
[metric computation stage](national_pipeline/06_metric_computation.md#run-the-stage) must have
finished. Each selected graph needs a row for every requested primary score and population
comparison used by the image sets, including an explicit undefined result where appropriate.
Unrelated levels and comparisons are not prerequisites for these images. Missing files or score
rows stop preparation. The source collection has no 1980 block or block-group boundaries, so these
histories start with the first supported configured year. After changing the selection, rerun
preparation before plotting; plotting uses the saved cohorts without selecting them again.

Each command accepts one or more workflow names, runs them in the supplied order, and stops if one
fails. Shared options apply to the whole invocation, so use separate commands when workflows need
different settings. Tables default to `results/` and images to `figures/`; change them with
`--data-directory` (both commands) and `--output-directory` (`make_figures.py` only). Relative
paths start at the repository root, and reruns replace matching outputs.

Preparation computes and validates all four tables before saving any of them. If a selection or
cohort check fails, existing tables remain unchanged. The files are written sequentially, so rerun
preparation before plotting if a write fails partway through.

## Find the components

National images are grouped by experiment, with each selection's images and legends kept together.
Their plotting inputs live under `results/national/processed_data/`, grouped by experiment.
Finished tables live under `results/national/tables/`, including the ranked population table and
rank-correlation summaries. Both CSV and Parquet copies of a finished table belong there; its
purpose, rather than its file format, determines the location.

National output names use `WB` for White–Black and `WPOC` for White–POC, followed by an uppercase
study-area type and two-digit definition year: `CBSA20`, `MAX_CITY20`, `MAX_COUNTY20`, or
`COUNTY20`. Census years remain four digits. Geography names are singular: `tract`, `block_group`,
`block`, and `county`. Shared result tables containing multiple selections live in a study-area
folder such as `CBSA20`; comparison-specific results use a prefix such as `WB_CBSA20`. For
example, entropy inputs live in `results/national/processed_data/entropy_by_geography/WB_CBSA20/`.
These labels affect output paths only; identifiers inside tables and pipeline input paths are
unchanged.

History images are saved under `figures/national/history/`, and their prepared tables under
`results/national/processed_data/history/<study_area_label>/`.

| Image set                         | Folder                             |
| --------------------------------- | ---------------------------------- |
| White–POC tract histories         | `WPOC_CBSA20_tract_histories/`     |
| White–Black tract histories       | `WB_CBSA20_tract_histories/`       |
| White–Black block-group histories | `WB_CBSA20_block_group_histories/` |
| White–Black block histories       | `WB_CBSA20_block_histories/`       |

These folder examples use `replication.yaml`; the study-area type and vintage follow the config.
Each image combines individual area histories, their arithmetic mean, and colored top-ten
histories. Names such as `TRACT_capy_histories.png` and `BLOCK_GROUP_capy_histories.png` identify
the geography and score. Both legends, `top_10_legend.png` and `individual_metro_legend.png`, live
alongside the images. The x-axis covers the configured years, with a gray band from 1980 to 1990
for blocks and block groups when 1980 is requested.

The prepared tables are `national_score_rows.parquet` (selected scores for eligible areas),
`eligible_areas.parquet`, `top_10_metros.parquet`, and `trajectory_rows.parquet` (the complete
histories that the panels draw). For style changes, edit
`code/national_figures/plot_national_results.py` and rerun only `make_figures.py`.
`plot_score_history()` keeps line styles, mean styling, ticks, grid lines, and shading together.
Year labels appear on every history image, including entropy histories. In that module, set
`HISTORY_X_TICK_LABELS` to override individual labels, for example `{1980: "'80", 1990: "'90"}`;
unspecified years retain their full labels. An empty string hides an individual label, while
`HISTORY_SHOW_X_TICK_LABELS = False` hides them all without removing the ticks or grid lines. The
function draws on the supplied axes and leaves them open; make image-specific adjustments in
`plot_national_figures()` after the drawing call and before `save_plot()`. Separate legends use
the plotted lines' styles, including their markers and widths.

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
exclude the following five CBSAs from every plotted year and all selected primary scores. The
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
comparison. Applying the same exclusion to all three scores keeps the decision consistent across
the image set, while removing every year preserves each metric's fixed cohort. Other negative
Moran scores remain eligible. This is a specific historical-coverage exclusion, not a general
cutoff on score values.

## Population composition

Prepare and draw the relationship between Black population share and each primary score:

```bash
uv run --locked python code/run_experiment.py population-composition --config code/configs/replication.yaml
uv run --locked python code/make_figures.py population-composition --config code/configs/replication.yaml
```

This set uses White–Black tract scores for areas with definition population above 100,000 and more
than 100,000 retained total residents in every configured decade. The population threshold
includes all groups, while the horizontal coordinate is Black/(White+Black). Each score keeps a
complete history cohort. Preparation saves those observations and the fitted linear relationships;
plotting reads both without fitting again. Images live in
`figures/national/population_composition/WB_CBSA20_tract_population_composition/`. Change
`YEAR_BASE_COLOR` near the top of `code/plotting/figure_style.py` to use shades of `AMBER`,
`PURPLE_HEART`, or another color. Its default keeps the fixed dark-to-light blue year palette.

## Score ranks

```bash
uv run --locked python code/run_experiment.py score-ranks --config code/configs/replication.yaml
uv run --locked python code/make_figures.py score-ranks --config code/configs/replication.yaml
```

The rank comparisons use every configured year, geographic level, and population comparison, with
a separate sample for each selection. Areas must have definition population above 100,000.
Preparation selects up to one hundred areas by retained population among those with finite values
for every selected primary metric. At least two primary metrics must be selected; omitted metrics
do not affect the cohort or produce images. Scores receive ascending ranks with average ranks for
ties. Saved rows and correlations carry the Census year, level, and comparison. Missing selected
score records stop preparation. Rank rows are saved under
`results/national/processed_data/score_ranks/<study_area_label>/`, and correlation summaries under
`results/national/tables/score_ranks/<study_area_label>/`.

Images share a comparison folder, such as
`figures/national/score_ranks/WB_CBSA20_score_rank_comparisons/`. Names begin with their year and
level, for example `2020_tract_dissimilarity_vs_capy.png`.

## Ranked population table

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

```bash
uv run --locked python code/run_experiment.py capy-weights --config code/configs/replication.yaml
uv run --locked python code/make_figures.py capy-weights --config code/configs/replication.yaml
```

This comparison uses tract graphs within CBSAs. The configuration must select CBSAs and include
tracts; other configured geography levels are ignored. Preparation selects up to one hundred ready
tract graphs by retained total population independently for each configured year. It calculates
quadratic Capy at neighbor weights zero, one, and the infinite-weight limit for every configured
population comparison. For a group with no neighbor interactions, its within-unit fraction
persists in that limit. Missing ready graphs or undefined scores stop preparation rather than
silently changing the ranked sample. Plotting also filters saved rows to tracts.

Plotting reads the saved ranks from
`results/national/processed_data/capy_weights/<study_area_label>/`. Each year and population
comparison gets a descriptively named tract PNG directly in `figures/national/capy_weights/`, for
example `WB_CBSA20_2020_tract_capy_neighbor_weights.png`. All selections share
`neighbor_weights_legend.png` in that directory.

## Entropy by geographic level

```bash
uv run --locked python code/run_experiment.py entropy-by-geography --config code/configs/replication.yaml
uv run --locked python code/make_figures.py entropy-by-geography --config code/configs/replication.yaml
```

Entropy histories use a separate complete cohort for each selected level, beginning at its first
supported configured year, with definition population above 100,000. Preparation selects the ten
most populous eligible metros from the study-area definitions and requires each to have a complete
history at every selected level. It saves their identities with the cohorts. Images and legends
live together in `figures/national/entropy_by_geography/WB_CBSA20_entropy_by_geography/`.
