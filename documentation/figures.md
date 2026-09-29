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

Preparation requires a configuration with 2020 CBSA study areas, all five census decades, and
tracts, block groups, and blocks; `replication.yaml` supplies all of these. It reads the study-area
definitions, every configured metric table, and `graph_outcomes.parquet`, so the [metric
computation stage](national_pipeline/06_metric_computation.md#run-the-stage) must have finished.
Preparation checks that every selected graph has `capy` rows for both population comparisons at all
three levels, which is why the levels are required. The tract histories also draw
`moran_row_standardized` and `dissimilarity` for the White–Black comparison. The pipeline computes
all of these by default; keep them in `metric_names`, and keep both entries in
`population_comparisons`, when narrowing a run.

Each command accepts one or more workflow names, runs them in the supplied order, and stops if one
fails. Shared options apply to the whole invocation, so use separate commands when workflows need
different settings. Tables default to `results/` and images to `figures/`; change them with
`--data-directory` (both commands) and `--output-directory` (`make_figures.py` only). Relative
paths start at the repository root, and reruns replace matching outputs.

## Find the components

Images are saved under `figures/national/`, and their prepared tables under
`results/national_figures/cbsa/2020/`.

| Image set                   | Folder                                   |
| --------------------------- | ---------------------------------------- |
| White–Black tract histories | `cbsa_2020_white_black_tract_histories/` |

The tract histories have separate all-metro and top-ten panels for Capy, row-standardized Moran's
I, and dissimilarity. Names such as `top_10_capy_tract_histories.png` and
`all_areas_capy_tract_histories.png` identify the selection, score, and geography. Both legends,
`top_10_legend.png` and `all_areas_legend.png`, live alongside the images.

The prepared tables are `national_score_rows.parquet` (the three scores for eligible metros),
`eligible_areas.parquet`, `top_10_metros.parquet`, and `trajectory_rows.parquet` (the complete
histories that the panels draw). For style changes, edit
`code/national_figures/plot_national_results.py` and rerun only `make_figures.py`.

## Selections and interpretation

Eligible metros have a 2020 definition population strictly above 100,000. The top ten are the ten
most populous eligible metros, with geographic ID breaking ties, chosen before any score-based
filtering. Each metric's histories then keep the eligible metros with a finite score in every
decade, subject to the historical exclusion below, so each metric has its own fixed cohort. A
top-ten metro without a complete history would appear in the legend without a line. Pale lines
show individual metros, and the blue mean gives each metro equal weight.

Capy includes self-pair terms and uses neighbor weight 1. It is read from the pipeline metric tables
alongside the other scores, which use graphs filtered to positive White-plus-Black population; see
[population filtering](national_pipeline/05_graph_construction.md#population-filtering-and-adjacency).

## Two-node historical graphs

White–Black tract histories exclude the following five CBSAs from every plotted year and all three
scores: Moran's I, dissimilarity, and Capy. The exclusion applies to both individual trajectories
and the mean across metros. It leaves the pipeline graphs and metric tables intact.

| CBSA code | Metro                           |
| --------- | ------------------------------- |
| 25940     | Hilton Head Island–Bluffton, SC |
| 29420     | Lake Havasu City–Kingman, AZ    |
| 35100     | New Bern, NC                    |
| 39150     | Prescott Valley–Prescott, AZ    |
| 39460     | Punta Gorda, FL                 |

Each metro's 1980 graph consists of two block-numbering areas (BNAs) from NHGIS's `US_bna_1980.shp`
layer, joined by one ordinary adjacency edge. Neither population filtering nor artificial
connections produced these two-node graphs. With unequal population shares, centering gives
deviations $a$ and $-a$, and row-standardized Moran's I is necessarily
$2a(-a)/(a^2+(-a)^2)=-1$. That value reflects the two-node representation rather than
distinguishing the strength of demographic clustering among these metros.

We omit their complete histories because this spatial resolution gives an uninformative 1980 Moran
comparison. Applying the same exclusion to all three scores keeps the decision consistent across
the image set, while removing every year preserves each metric's fixed cohort. Other negative Moran
scores remain eligible. This is a specific historical-coverage exclusion, not a general cutoff on
score values.
