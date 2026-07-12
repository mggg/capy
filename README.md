## Project Purpose

This project downloads population and geography data from the Census Bureau API and IPUMS/NHGIS, constructs adjacency graphs where census units (e.g. tracts) within study areas (e.g. CBSAs) are connected if they share a border, and applies a battery of residential segregation metrics. The goal is to assess segregation and disagreement among metrics across geographies and decades.

## Pipeline overview

The full pipeline is driven by `scripts/reproduce.sh`, which sources `scripts/pipeline_config.sh` for all configuration. Steps run in order:

1. **`scripts/setup.sh`** — scaffolds the directory tree (`census_raw/`, `census_geographies/`, `study_area_sources/`, `study_areas/`, `outputs/`, etc.)
2. **`pipeline/download_population_tables.py`** — downloads decennial census race/ethnicity counts (TOTPOP, WHITE, BLACK, POC, etc.) via Census API; uses IPUMS/NHGIS extracts for 1980 and 1990
3. **`pipeline/download_geographies.py`** — downloads TIGER/Line shapefiles (2000–2020 via Census API; 1980/1990 via IPUMS NHGIS)
4. **`pipeline/build_census_geographies.py`** — joins population tables to shapefiles, producing one attributed shapefile per year/level in `census_geographies/`
5. **`scripts/build_study_areas.sh`** → **`pipeline/build_study_areas.py`** — builds study area boundary polygons (e.g. CBSA outlines from county-component `.xls` files) into `study_areas/definitions/`
6. **`scripts/overlaps.sh`** → **`pipeline/overlaps.py`** — clips census geography shapefiles to each study area boundary (parallelized over years); outputs clipped shapefiles to `study_areas/<year>/` and coverage stats to `outputs/<run>/coverage_stats.csv`
7. **`pipeline/gen_duals.py`** — builds the dual adjacency graph from each clipped shapefile; contracts zero-population nodes and ensures full connectivity; outputs `*_orig.json` and `*_connected.json` alongside each shapefile
8. **`pipeline/calculate_metrics.py`** — computes ~80 segregation metrics per study area / year from each connected graph JSON; outputs one CSV row per area; errors logged to `outputs/<run>/metric_failures.csv`
9. **`pipeline/generate_figures.py`** — reads aggregated metric CSVs and produces publication figures

## Configuration

All pipeline behavior is controlled by environment variables (with defaults in `scripts/pipeline_config.sh`):

| Variable | Default | Options |
|---|---|---|
| `STUDY_AREA_TYPE` | `cbsa` | `cbsa`, `county` |
| `CENSUS_GEOGRAPHY_TYPE` | `tracts` | `tracts`, `block_groups`, `blocks`, `counties` |
| `CENSUS_GEOGRAPHY_YEARS` | `2020 2010 2000 1990 1980` | space-separated year list |
| `STUDY_AREA_VINTAGE` | `2020` | year |
| `RUN_NAME` | `<geo_type>_in_<study_area_type>` | string |
| `RUN_OUTPUT_DIR` | `outputs/<RUN_NAME>` | path |

For `STUDY_AREA_TYPE=cbsa`, a delineation file matching `list1_*_<vintage>.xls` must exist in `study_area_sources/`. A Census API key and IPUMS API key are required for downloads.

## Important directories

| Directory | Contents | Notes |
|---|---|---|
| `study_area_sources/` | CBSA delineation `.xls` files |
| `census_raw/geographies/` | Raw downloaded TIGER/NHGIS shapefiles |
| `census_raw/population/` | Raw downloaded population CSV tables | 
| `census_geographies/` | Merged population+shapefile per year/level (`<year>_<level>.shp`) |
| `study_areas/definitions/` | Study area boundary shapefiles | 
| `study_areas/<year>/` | Clipped census shapefiles + dual graph JSONs per study area | 
| `outputs/<run_name>/` | Metric CSVs (`white_black.csv`, `white_poc.csv`), `coverage_stats.csv`, `metric_failures.csv`, figures, `run.log` |

`_orig.json` = raw dual graph; `_connected.json` = fully connected, zero-pop nodes contracted (used for metrics).

## Important commands

- **Setup:** `bash scripts/setup.sh`
- **Full reproduction:** `bash scripts/reproduce.sh` (takes many hours on full dataset)
- **Generate dual graphs:** `python pipeline/gen_duals.py <shapefile.shp> <out_orig.json> <out_connected.json>`
- **Calculate metrics:** `python pipeline/calculate_metrics.py <connected.json> <x_col> <y_col> <tot_col>`
- **Generate figures:** `python pipeline/generate_figures.py --filename <metrics.csv> --prefix <prefix>`
- **Check overlaps:** `bash scripts/overlaps.sh`
- **Parse output:** `python pipeline/parse_output.py` (consumes CSV format)


### Dependencies
Python deps are managed via Poetry:
```
pip install poetry
poetry install
```

To launch a shell with the poetry enviroment activated, run:
```
poetry shell
```

Set API keys in your shell before downloading data:
```
export CENSUS_API_KEY="..."
export IPUMS_API_KEY="..."
```