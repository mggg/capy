Code in this folder creates tables and visualizations of the metrics calcualted in `../capy_core`.

Folders and scripts:

+ `latex_tables/`: creates tables used in the Appendix of the paper, showing area values and ranks. Scripts can be configured to rank by various metrics but default to Capy.
+ `line_plots/`: these scripts create metric line plots used in the paper.
+ `metrics_vs_rho/`: creates scatterplots showing how areas score on a given metric versus rho (the share of the minority population). The minority population can be configured as Black or POC (total minus White).
+ `rank_comparisons/`: creates rank comparison scatterplots with Capy, Moran's I, or Dissimilarity.
+ `../../visualization_settings.py`: contains shared style decisions and helper functions used across experiment scripts.
+ `lambda_scripts/`: plots the rankings of metro areas according to capy against their rankings accoding to lambda weighted variants of capy.
+ `chicago_maup/`: plots various segregation metrics on the city of Chicago at the tract, block group, and block levels

## Line plots

`line_plots/generate_figures.py` creates the individual metric line plots, grid line plots, and metric-family grids. For metrics stored under the standard `data/shared/outputs/<geography>_in_<study_area>/` layout, it infers the geography and study-area types from the input directory. For example:

```bash
poetry run python experiment_code/baseline/visualization/line_plots/generate_figures.py \
    --filename data/shared/outputs/counties_in_cbsa/white_black.csv \
    --prefix white_black
```

This writes figures under `figures/baseline/counties_in_cbsa/`. Use `--geography-type` or `--study-area-type` to override the inferred values when an input CSV does not follow the standard directory layout.

## Rho versus metric scatterplots

`metrics_vs_rho/metrics_vs_rho.py` plots each metric against the minority population share. For example:

```bash
poetry run python experiment_code/baseline/visualization/metrics_vs_rho/metrics_vs_rho.py \
    --filename data/shared/outputs/tracts_in_cbsa/white_black.csv
```

The plotter includes only study areas that have observations in all five Census years (1980, 1990, 2000, 2010, and 2020) and whose population remains above 100,000 in every year. It reports an error if no observations meet both requirements. Figures are written under `figures/baseline/<geography>_in_<study_area>/metrics_vs_rho/`; use `--output-dir` to override that location.

## LaTeX tables

The scripts under `latex_tables/` generate `.tex` table fragments for inclusion in the paper appendix:

```bash
poetry run python experiment_code/baseline/visualization/latex_tables/latex_table_one_year.py
poetry run python experiment_code/baseline/visualization/latex_tables/latex_table_all_years.py
```

Configure the input CSV, ranking metric, displayed columns, number of areas, and output path using the editable constants near the top of each script. The one-year table also provides `YEAR_FILTER`. The table provides `YEARS` and `RANK_YEAR`.

The multi-year table defaults to `YEARS = [1990, 2000, 2010, 2020]`, independently of the years selected for the data pipeline. To include all five Census decades, change it to:

```python
YEARS = [1980, 1990, 2000, 2010, 2020]
```

By default, generated tables are written under `figures/baseline/<geography>_in_<study_area>/latex_tables/`.
