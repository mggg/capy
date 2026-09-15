# Line plots

Trace plots showing segregation metrics over time for census areas.

Run scripts from the project root.

---

## `generate_figures.py`

Generates all line-plot figure types at once (individual metric lines, grid lineplots, and metric family grids). Example use:

```bash
# white-Black, tracts in CBSA (defaults)
python experiment_code/baseline/visualization/line_plots/generate_figures.py

# white-Black
python experiment_code/baseline/visualization/line_plots/generate_figures.py \
    --filename data/shared/outputs/tracts_in_cbsa/white_black.csv \
    --prefix white_black

# white-POC
python experiment_code/baseline/visualization/line_plots/generate_figures.py \
    --filename data/shared/outputs/tracts_in_cbsa/white_poc.csv \
    --prefix white_poc
```

---

## Individual scripts

### `plot_grid_top10.py` — top 10 most populated metros

```bash
python experiment_code/baseline/visualization/line_plots/plot_grid_top10.py \
    --filename data/shared/outputs/tracts_in_cbsa/white_black.csv
```

### `plot_grid_all_census_areas.py` — all eligible CBSAs (population ≥ 100k, present in all years)

```bash
python experiment_code/baseline/visualization/line_plots/plot_grid_all_census_areas.py \
    --filename data/shared/outputs/tracts_in_cbsa/white_black.csv
```

### `plot_family_grids.py` — one panel grid per metric family

```bash
python experiment_code/baseline/visualization/line_plots/plot_family_grids.py \
    --filename data/shared/outputs/tracts_in_cbsa/white_black.csv
```
