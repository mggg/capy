## Project Purpose

This project downloads population and geography data from the Census Bureau API and IPUMS/NHGIS, constructs adjacency graphs where census units (e.g. tracts) within study areas (e.g. CBSAs) are connected if they share a border, and applies a battery of residential segregation metrics. The goal is to assess segregation and disagreement among metrics across geographies and decades.

## Folder structure

```
capy-bara/
├── data/
│   ├── raw/                        # downloaded source files (gitignored)
│   │   ├── geographies/            # TIGER/Line and NHGIS shapefiles
│   │   ├── population/             # Census API / NHGIS population tables
│   │   └── ipums_extracts/         # IPUMS extracts (1980, 1990)
│   ├── interim/                    # processed intermediates (gitignored)
│   │   ├── census_geographies/     # population-attributed shapefiles per year/level
│   │   ├── cbsas/                  # CBSA definitions by decade
│   │   ├── study_areas/            # clipped shapefiles + dual graph JSONs per study area
│   │   └── study_area_sources/     # CBSA delineation .xls files
│   └── outputs/                    # pipeline run outputs
│       ├── tracts_in_cbsa/
│       ├── block_groups_in_cbsa/
│       ├── blocks_in_cbsa/
│       └── cross_level_comparisons/  # figures comparing results across runs
│
├── pipeline/                       # core pipeline modules
│   ├── download/                   # download_geographies.py, download_population_tables.py
│   ├── build/                      # build_census_geographies.py, build_study_areas.py,
│   │                               #   overlaps.py, gen_duals.py, filter_cbsas.py
│   ├── metrics/                    # calculate_metrics.py, parse_output.py
│   ├── viz/                        # generate_figures.py
│   ├── utils/                      # definitions.py
│   └── tests/
│
├── experiments/                    # hypothesis-testing experiments
│   ├── notebooks/                  # scratch notebooks before a hypothesis becomes a script
│   ├── comparisons/                # cross-experiment analyses and figures
│   └── exp_<name>/                 # one folder per experiment: run.py + figures/
│
├── working_paper_reproduction/     # materials for reproducing paper results
│   ├── notebooks/                  # reproduction notebooks
│   ├── misc_analysis/
│   └── figures/
│
├── scripts/                        # shell scripts for running the pipeline
└── archive/                        # inactive code and old outputs
```

## Pipeline overview

The full pipeline is driven by `scripts/reproduce.sh`, which sources `scripts/pipeline_config.sh` for all configuration. Steps run in order:

1. **`scripts/setup.sh`** — scaffolds the directory tree
2. **`pipeline/download/download_population_tables.py`** — downloads decennial census race/ethnicity counts (TOTPOP, WHITE, BLACK, POC, etc.) via Census API; uses IPUMS/NHGIS extracts for 1980 and 1990
3. **`pipeline/download/download_geographies.py`** — downloads TIGER/Line shapefiles (2000–2020 via Census API; 1980/1990 via IPUMS NHGIS)
4. **`pipeline/build/build_census_geographies.py`** — joins population tables to shapefiles, producing one attributed shapefile per year/level in `data/interim/census_geographies/`
5. **`scripts/build_study_areas.sh`** → **`pipeline/build/build_study_areas.py`** — builds study area boundary polygons (e.g. CBSA outlines from county-component `.xls` files) into `data/interim/study_areas/definitions/`
6. **`scripts/overlaps.sh`** → **`pipeline/build/overlaps.py`** — clips census geography shapefiles to each study area boundary (parallelized over years); outputs clipped shapefiles to `data/interim/study_areas/<year>/` and coverage stats to `data/outputs/<run>/coverage_stats.csv`
7. **`pipeline/build/gen_duals.py`** — builds the dual adjacency graph from each clipped shapefile; contracts zero-population nodes and ensures full connectivity; outputs `*_orig.json` and `*_connected.json` alongside each shapefile
8. **`pipeline/metrics/calculate_metrics.py`** — computes ~80 segregation metrics per study area / year from each connected graph JSON; outputs one CSV row per area; errors logged to `data/outputs/<run>/metric_failures.csv`
9. **`pipeline/viz/generate_figures.py`** — reads aggregated metric CSVs and produces publication figures

`_orig.json` = raw dual graph; `_connected.json` = fully connected, zero-pop nodes contracted (used for metrics).

## Configuration

All pipeline behavior is controlled by environment variables (with defaults in `scripts/pipeline_config.sh`):

| Variable | Default | Options |
|---|---|---|
| `STUDY_AREA_TYPE` | `cbsa` | `cbsa`, `county` |
| `CENSUS_GEOGRAPHY_TYPE` | `tracts` | `tracts`, `block_groups`, `blocks`, `counties` |
| `CENSUS_GEOGRAPHY_YEARS` | `2020 2010 2000 1990 1980` | space-separated year list |
| `STUDY_AREA_VINTAGE` | `2020` | year |
| `RUN_NAME` | `<geo_type>_in_<study_area_type>` | string |
| `RUN_OUTPUT_DIR` | `data/outputs/<RUN_NAME>` | path |

For `STUDY_AREA_TYPE=cbsa`, a delineation file matching `list1_*_<vintage>.xls` must exist in `data/interim/study_area_sources/`. A Census API key and IPUMS API key are required for downloads.

## Important commands

- **Setup:** `bash scripts/setup.sh`
- **Full reproduction:** `bash scripts/reproduce.sh` (takes many hours on full dataset)
- **Generate dual graphs:** `python pipeline/build/gen_duals.py <shapefile.shp> <out_orig.json> <out_connected.json>`
- **Calculate metrics:** `python pipeline/metrics/calculate_metrics.py <connected.json> <x_col> <y_col> <tot_col>`
- **Generate figures:** `python pipeline/viz/generate_figures.py --filename <metrics.csv> --prefix <prefix>`
- **Check overlaps:** `bash scripts/overlaps.sh`
- **Parse output:** `python pipeline/metrics/parse_output.py`

## Dependencies

Python deps are managed via Poetry:
```
pip install poetry
poetry install
```

To launch a shell with the poetry environment activated:
```
poetry shell
```

Set API keys in your shell before downloading data:
```
export CENSUS_API_KEY="..."
export IPUMS_API_KEY="..."
```
