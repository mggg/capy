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

- [Shared color palette](#shared-color-palette)
- [National score histories](#national-score-histories)
- [Figure components and saved tables](#figure-components-and-saved-tables)
- [Reading the saved tables](#reading-the-saved-tables)
- [Selections and interpretation](#selections-and-interpretation)
- [Two-node historical graphs](#two-node-historical-graphs)
- [History plot styling](#history-plot-styling)
- [Population composition](#population-composition)
- [Score ranks](#score-ranks)
- [Ranked population table](#ranked-population-table)
- [Capy neighbor weights](#capy-neighbor-weights)
- [Entropy by geographic level](#entropy-by-geographic-level)
- [Grid versus national scores](#grid-versus-national-scores)

## Shared color palette

The paper figures draw from the palette below, whose hex values follow
[GerryTools' LaTeX color table](https://github.com/mggg/gerrytools/blob/main/gerrytools/colors/_latex_table.py).
The table includes the full preferred palette, including colors not currently used in a figure.
Its definitions are stored in [`figure_style.py`](../code/plotting/figure_style.py).

| Color               | Hex value |
| ------------------- | --------- |
| Apple green         | `#8db600` |
| Alizarin            | `#d11a42` |
| Slate gray          | `#708090` |
| Amber               | `#ffbf00` |
| Mikado yellow       | `#ffc40c` |
| Cadmium green       | `#006b3c` |
| Forest green (web)  | `#228b22` |
| Lust                | `#e62020` |
| Denim               | `#1560bd` |
| Purple heart        | `#69359c` |
| Cherry blossom pink | `#ffb7c5` |
| Dark tangerine      | `#ffa812` |
| Banana yellow       | `#ffe135` |
| Light blue          | `#add8e6` |


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

You can prepare or render several workflows in one invocation by supplying their names in order.
They share the invocation’s options, and a failure stops subsequent workflows. Tables go to
`results/` by default and images to `figures/`, with `--data-directory` available in both commands
and `--output-directory` available in `make_figures.py` to change those roots.

Relative result and figure paths start at the repository root. A relative `--config` path instead
starts at the shell’s current directory unless the option is omitted and the command uses the
repository’s `code/configs/replication.yaml`. Reruns replace matching outputs.

For `national`, preparation computes and validates all four history tables before saving any of
them. A selection or cohort-check failure therefore leaves existing tables unchanged. Writes are
sequential, however, so a failure during saving can leave an incomplete set that requires another
preparation run before plotting.

## Figure components and saved tables

Each national analysis keeps a selection’s images and legends together, with its plotting inputs
saved separately under `results/national/processed_data/`. Finished publication tables belong
under `results/national/tables/`, where ranked population tables have CSV and Parquet copies and
rank-correlation summaries are available as Parquet.

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

## Reading the saved tables

The following two-row excerpts come from saved results, with decimals rounded to four places and
`null` marking missing values. For wide tables, the preview shows selected columns and the
accompanying explanation covers the remaining fields.

Load these ordinary, geometry-free tables with `pandas.read_parquet()` and use their identity
columns for joins since writers omit the pandas index. The types described below express the
meaning of the data rather than a fixed pandas/Arrow representation: a nullable population column
may load as floating point while still counting whole people. Shares are fractions rather than
percentages, and scores are dimensionless, including valid negative values of Moran’s I.

Within a study-area folder, a **selection** is the combination of integer `census_year`, text
`geography_level`, and text `population_comparison`. Stored levels retain pipeline values
`tracts`, `block_groups`, `blocks`, or `counties` even though output path labels use singular
names. Comparisons are `white_black` or `white_poc`. Preserve `study_area_id` (such as
`cbsa_16980`) and any geographic codes as strings. The folder identifies the fixed study-area type
and vintage, so include that context when combining folders.

### Selected scores: `national_score_rows.parquet`

In `history/<study_area_label>/`, this table contains the selected scores for population-eligible
areas. For example:

| `study_area_id` | `census_year` | `geography_level` | `population_comparison` | `metric`      | `value` |
| --------------- | ------------- | ----------------- | ----------------------- | ------------- | ------- |
| cbsa_10180      | 1980          | tracts            | white_black             | dissimilarity | 0.5087  |
| cbsa_10180      | 1980          | tracts            | white_black             | entropy_index | 0.1995  |

The two rows belong to the same area, year, graph resolution, and population comparison, but
report different formulas in `metric` and their results in `value`. This is the long score format:
an area’s scores occupy several rows, distinguished by `study_area_id`, `census_year`,
`geography_level`, `population_comparison`, and `metric`.

Two omitted columns explain outcomes that the numeric preview does not show. `graph_status`
preserves the upstream graph result while `undefined_reason` explains a null score even when the
graph is ready. Such an explicit undefined result remains a valid score record, unlike a missing
requested row. The
[metric output contract](national_pipeline/06_metric_computation.md#saved-tables-and-yearly-averages)
describes the outcomes and reason codes.

### Complete histories: `trajectory_rows.parquet`

| `study_area_id` | `census_year` | `geography_level` | `population_comparison` | `metric`               | `value` |
| --------------- | ------------- | ----------------- | ----------------------- | ---------------------- | ------- |
| cbsa_10180      | 1980          | tracts            | white_black             | moran_row_standardized | 0.3507  |
| cbsa_10180      | 1990          | tracts            | white_black             | moran_row_standardized | 0.3164  |

Here the same area’s Moran history moves from 0.3507 in 1980 to 0.3164 in 1990. The columns match
the selected-score table, but inclusion now requires finite values in every required year for the
metric and comparison after applying the historical exclusions. That restriction gives the
renderer a complete saved trajectory for each retained area. All `undefined_reason` values are
therefore null, with `graph_status` still preserving the upstream outcome.

### Eligible areas: `eligible_areas.parquet`

| `study_area_id` | `name`                                | `definition_year` | `definition_population` |
| --------------- | ------------------------------------- | ----------------- | ----------------------- |
| cbsa_35620      | New York-Newark-Jersey City, NY-NJ-PA | 2020              | 20140470                |
| cbsa_31080      | Los Angeles-Long Beach-Anaheim, CA    | 2020              | 13200998                |

These populations describe the fixed 2020 area definitions rather than changing with each
observation year in a score history. `definition_year` records that vintage and
`definition_population` its resident count, paired with the area’s display `name`. Use
`study_area_id` to attach this one-row-per-area information to the score tables.

The file preserves all upstream definition columns except `geometry`. Other fields include text
`study_area_type`, `metro_code`, and `metro_name`; lists of text county codes in `county_codes`
and `metro_county_codes`; and selection-specific `selected_county_code`, `selected_place_code`,
and `selection_reason`. Inapplicable fields can be null, and fields vary by study-area type. Their
meanings follow the
[study-area output guide](national_pipeline/04_study_area_assignment.md#read-the-outputs).

### Highlighted areas: `top_10_metros.parquet`

| `study_area_id` | `name`                                | `definition_population` |
| --------------- | ------------------------------------- | ----------------------- |
| cbsa_35620      | New York-Newark-Jersey City, NY-NJ-PA | 20140470                |
| cbsa_31080      | Los Angeles-Long Beach-Anaheim, CA    | 13200998                |

The two largest eligible definitions head this ten-area highlight list, which preserves the
columns of `eligible_areas.parquet` and its descending population order, breaking ties by area ID.
That saved order determines the legend while `study_area_id` connects each highlight to its
trajectory. Color and rank are assigned outside the table. Other workflows have their own copies
of this definition table, selected as described in their respective sections.

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
population, as described under
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

History images, including entropy plots, show all year labels by default. Use
`HISTORY_X_TICK_LABELS` to override particular labels, for example `{1980: "'80", 1990: "'90"}`,
leaving unspecified years in full. An empty string suppresses one label; setting
`HISTORY_SHOW_X_TICK_LABELS = False` suppresses them all while retaining ticks and grid lines.
Because `plot_score_history()` leaves the supplied axes open, further adjustments can be made in
`plot_national_figures()` before `save_plot()`. Separate legends inherit the plotted lines’
styles, including markers and widths.

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
relationships. Rendering reconstructs each line from its saved endpoints without refitting the
individual observations.

For images in `figures/national/population_composition/`, the year palette is controlled by
`YEAR_COLORS` in [`figure_style.py`](../code/plotting/figure_style.py). By default,
`YEAR_BASE_COLOR = None` preserves the separate blue, green, light-green, amber, and red colors
assigned to 1980 through 2020. Set `YEAR_BASE_COLOR` to `AMBER`, `PURPLE_HEART`, or another color
to replace that palette with shades progressing from dark to light across the years.

### Saved composition format

Under `results/national/processed_data/population_composition/<study_area_label>/`, the
observations in `composition_rows.parquet` look like this:

| `study_area_id` | `census_year` | `metric`               | `retained_WHITE` | `retained_BLACK` | `rho`  | `value` |
| --------------- | ------------- | ---------------------- | ---------------- | ---------------- | ------ | ------- |
| cbsa_10180      | 1980          | moran_row_standardized | 114111           | 7350             | 0.0605 | 0.3507  |
| cbsa_10180      | 1990          | moran_row_standardized | 117214           | 7989             | 0.0638 | 0.3164  |

In these observations, the retained Black and White counts determine the horizontal coordinate `rho
= retained_BLACK / (retained_WHITE + retained_BLACK)`, and the Moran score in `value` determines the
vertical coordinate. The full rows retain the long score identity and columns, restricted to
White–Black tracts, and add `retained_TOTPOP` alongside the displayed whole-person counts. Each
metric’s cohort must have finite scores throughout its history, so the areas plotted can differ
between metrics.

The corresponding `composition_fits.parquet` stores line endpoints:

| `metric`               | `census_year` | `rho`  | `value` |
| ---------------------- | ------------- | ------ | ------- |
| moran_row_standardized | 1980          | 0.0003 | 0.3196  |
| moran_row_standardized | 1980          | 0.4327 | 0.6452  |

The two rows locate one fitted line at the minimum and maximum observed population shares in 1980.
For each endpoint, `rho` is the share and `value` the fitted Moran score, with `metric`,
`census_year`, and `rho` together identifying the row. Every metric/year fit is saved this way,
allowing the renderer to reconstruct the line from its endpoints without refitting the individual
observations. The file contains neither slope/intercept columns nor confidence intervals.

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

### Saved rank format

The plotting inputs in `rank_rows.parquet` include:

| `study_area_id` | `census_year` | `geography_level` | `population_comparison` | `capy` | `capy_rank` |
| --------------- | ------------- | ----------------- | ----------------------- | ------ | ----------- |
| cbsa_35620      | 2020          | tracts            | white_black             | 0.7737 | 98          |
| cbsa_31080      | 2020          | tracts            | white_black             | 0.7228 | 94          |

In the displayed 2020 White–Black tract sample, New York’s higher Capy score gives it a higher
`capy_rank` than Los Angeles. Rankings run from one for the lowest score and average the positions
of tied areas, so fractional ranks are possible. Each selection and `study_area_id` identifies one
row, carrying finite scores and corresponding `<metric>_rank` columns for the selected primary
metrics: `capy`, `dissimilarity`, and `moran_row_standardized`.

The full plotting input also retains the whole-person count `retained_TOTPOP` used to select the
sample. Unselected metrics contribute no columns, and the renderer reads the saved ranks directly.

The finished `rank_correlations.parquet` summarizes pairs of score rankings:

| `census_year` | `geography_level` | `population_comparison` | `x_metric` | `y_metric`             | `area_count` | `spearman` |
| ------------- | ----------------- | ----------------------- | ---------- | ---------------------- | ------------ | ---------- |
| 2020          | tracts            | white_black             | capy       | dissimilarity          | 100          | 0.8861     |
| 2020          | tracts            | white_black             | capy       | moran_row_standardized | 100          | 0.7642     |

Across these 100 areas, Capy’s ranking agrees more closely with dissimilarity than with Moran, as
indicated by the larger `spearman` correlation. The comparison is identified by the selection and
its `x_metric`/`y_metric` pair, with `area_count` recording the sample size. If a sample has only
one area or a metric is constant, the correlation can be null without an accompanying reason
column. This finished summary is separate from the rank rows used to draw the scatterplots.

## Ranked population table

The ranked population table lists the areas with the highest Capy scores alongside their
populations and supplementary metrics. The `ranked-population-table` workflow produces finished
tables without a corresponding figure set.

```bash
uv run --locked python code/run_experiment.py ranked-population-table --config code/configs/replication.yaml
```

For each configured year, geographic level, and population comparison, preparation saves up to one
hundred areas with the highest finite Capy scores. Definition population must exceed 100,000, and
score ties are broken by area ID. Capy is required, with other selected primary metrics appearing
as supplementary columns. Undefined supplementary scores remain null.

Each row includes its selection identifiers, rank, area identity, selected scores, retained
population in millions, and the second group's share of total retained population. This share
includes groups outside the White–Black comparison in its denominator. CSV and Parquet copies are
saved under `results/national/tables/ranked_population_table/<study_area_label>/`.

### Saved ranked-population format

For example, the finished population table includes:

| `rank` | `study_area_id` | `census_year` | `geography_level` | `population_comparison` | `capy` | `population_millions` | `second_group_share_total_population` |
| ------ | --------------- | ------------- | ----------------- | ----------------------- | ------ | --------------------- | ------------------------------------- |
| 1      | cbsa_33340      | 2020          | tracts            | white_black             | 0.7780 | 1.5747                | 0.1589                                |
| 2      | cbsa_16980      | 2020          | tracts            | white_black             | 0.7762 | 9.6185                | 0.1607                                |

These entries lead the 2020 White–Black tract list because they have the highest finite Capy
scores. The integer `rank` starts at one and breaks score ties by area ID, making either rank or
`study_area_id` sufficient to identify a row within a selection. Both `top_100_capy.parquet` and
`top_100_capy.csv` save the same entries, including the omitted display `name` and any selected
supplementary `dissimilarity` or `moran_row_standardized` scores. Those supplementary scores may
be null, but their undefined reasons are not retained in this wide table.

Read `population_millions` as retained total population divided by 1,000,000 and
`second_group_share_total_population` as retained Black or POC population divided by that full
total, according to `population_comparison`. Including all residents in this denominator
distinguishes the share from composition `rho` and grid-comparison `group_share`, which use only
the two compared groups. The finished table drops the raw count columns and needs no rendering
step. When reading its CSV copy, preserve text identifiers and interpret empty fields as nulls.

## Capy neighbor weights

The `capy-weights` analysis compares area rankings at neighbor weights zero, one, and the
infinite-weight limit of quadratic Capy. It reads tract graphs directly, so completed graph
archives are required:

```bash
uv run --locked python code/run_experiment.py capy-weights --config code/configs/replication.yaml
uv run --locked python code/make_figures.py capy-weights --config code/configs/replication.yaml
```

With CBSAs and tracts selected in the configuration, preparation chooses up to one hundred ready
tract graphs per year by retained total population, ignoring other geography levels. It then
calculates all three weights for every configured population comparison on that year’s selected
graphs. To preserve the sample, a missing ready graph or undefined score stops preparation rather
than removing an area. Plotting likewise restricts saved rows to tracts.

In the infinite-weight limit, a group with no neighbor interactions retains its within-unit
fraction.

Plotting reads the saved ranks from
`results/national/processed_data/capy_weights/<study_area_label>/`. Each year and population
comparison gets a descriptively named tract PNG directly in `figures/national/capy_weights/`, for
example `WB_CBSA20_2020_tract_capy_neighbor_weights.png`. All selections share
`neighbor_weights_legend.png` in that directory.

### Saved neighbor-weight format

The weight comparison is saved in `capy_weights.parquet`:

| `study_area_id` | `census_year` | `population_comparison` | `zero` | `unit` | `limit` |
| --------------- | ------------- | ----------------------- | ------ | ------ | ------- |
| cbsa_35620      | 1980          | white_black             | 0.8321 | 0.7804 | 0.7682  |
| cbsa_35620      | 1980          | white_poc               | 0.7692 | 0.7321 | 0.7234  |

Reading across either row compares one graph’s scores at zero neighbor weight, unit weight, and
the infinite-weight limit. Reading down compares the White–Black and White–POC populations on that
graph. A row is identified by its selection and `study_area_id`, with the omitted `name` providing
a display label and `geography_level` always set to `tracts`.

For plotting, the corresponding `zero_rank`, `unit_rank`, and `limit_rank` columns order the
selected areas within each year/comparison, starting at one for the lowest score and averaging
ties. All three scores must be defined before the table is published, so it has no reason columns.
The population counts used to choose the sample are not retained.

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

### Saved entropy format

Under `results/national/processed_data/entropy_by_geography/WB_<study_area_label>/`,
`entropy_histories.parquet` contains observations such as:

| `study_area_id` | `census_year` | `geography_level` | `metric`      | `value` |
| --------------- | ------------- | ----------------- | ------------- | ------- |
| cbsa_10180      | 1980          | tracts            | entropy_index | 0.1995  |
| cbsa_10180      | 1990          | tracts            | entropy_index | 0.1526  |

The example follows one area’s tract entropy from 1980 to 1990. Each row retains the long score
columns used for national histories, with `metric = entropy_index` and `population_comparison =
white_black`, and all included values are finite. The cohort is selected separately by level without
the main history workflow’s five-area 1980 exclusion.

Its companion `top_10_metros.parquet` identifies the highlighted areas:

| `study_area_id` | `name`                                | `definition_population` |
| --------------- | ------------------------------------- | ----------------------- |
| cbsa_35620      | New York-Newark-Jersey City, NY-NJ-PA | 20140470                |
| cbsa_31080      | Los Angeles-Long Beach-Anaheim, CA    | 13200998                |

As in the eligible-area table, each row preserves a study-area definition, ordered here by
descending definition population with area-ID tie breaking. Before these identities are joined to
entropy histories by `study_area_id`, preparation requires every highlighted area to have a
complete history at each selected level.

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

Prepared tables live under
`results/national/processed_data/grid_vs_national_scores/<study_area_label>/`, such as `CBSA20` or
`MAX_CITY20`. Images live under `figures/national/grid_vs_national_scores/`, with names such as
`TRACT_grid_v_nat_capy_by_share.png` and `TRACT_grid_v_nat_top_10_capy_by_share.png`. The samples
share `top_10_legend.png` and `reference_legend.png`.

### Saved grid-comparison format

The national observations in `tract_scores.parquet` include:

| `study_area_id` | `census_year` | `population_comparison` | `retained_WHITE` | `retained_BLACK` | `group_share` | `capy` |
| --------------- | ------------- | ----------------------- | ---------------- | ---------------- | ------------- | ------ |
| cbsa_10180      | 2020          | white_black             | 110356           | 13076            | 0.1059        | 0.5237 |
| cbsa_10180      | 2020          | white_poc               | 110356           | 13076            | 0.3750        | 0.5307 |

The two rows compare White–Black and White–POC populations in the same area’s 2020 tract graph. For
White–Black, the displayed counts give `group_share = retained_BLACK / (retained_WHITE +
retained_BLACK)`. White–POC instead uses `retained_POC`, which is retained in the full table but
omitted from this preview. Either share is null if the combined population in its denominator is
zero.

Here, `study_area_id`, integer `census_year` (2020), and text `population_comparison` identify a
row, with no `geography_level` column because all observations use tracts. Text `name` and
`metro_code` provide area labels, and the three retained population columns preserve whole-person
counts alongside the separate score columns.

Selected comparison metrics occupy their own nullable numeric columns, named for the formulas in
the [metric guide](national_pipeline/06_metric_computation.md). Pivoting the long input into this
wide format preserves undefined scores as nulls but drops `undefined_reason` and `graph_status`,
so consult the pipeline metric table for the explanation of a missing value. Metrics that were not
selected have no columns.

The saved `reference_scores.parquet` supplies the comparison curves:

| `arrangement` | `metric`      | `group_share` | `value` |
| ------------- | ------------- | ------------- | ------- |
| cluster       | dissimilarity | 0.0050        | 1       |
| cluster       | dissimilarity | 0.0060        | 1       |

Each row is a reference score for one arrangement, metric, and population share. The
[experiment guide](experiments.md#saved-grid-tables-and-arrays) explains these curve families and
omitted combinations. The renderer compares the empirical score columns with reference rows having
the corresponding `metric`.

Finally, `top_10_metros.parquet` identifies the highlighted definitions:

| `study_area_id` | `name`                                | `metro_code` |
| --------------- | ------------------------------------- | ------------ |
| cbsa_35620      | New York-Newark-Jersey City, NY-NJ-PA | 35620        |
| cbsa_31080      | Los Angeles-Long Beach-Anaheim, CA    | 31080        |

The fixed metro code list determines both which area definitions appear here and their order,
independently of the sample’s scores or population counts. The full file preserves the definition
columns described above. By joining `study_area_id` to the observations, the renderer can
highlight these areas while drawing their scores against the saved reference curves.
