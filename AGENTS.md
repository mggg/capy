## Project Purpose

This project downloads population and geography data from the Census Bureau API and IPUMS/NHGIS, constructs adjacency graphs where census units (e.g. tracts) within study areas (e.g. CBSAs) are connected if they share a border, and applies a battery of residential segregation metrics. The goal is to assess segregation and disagreement among metrics across geographies and decades.

## Pipeline overview

The full pipeline is driven by `scripts/reproduce.sh`. Configuration lives in `pipeline/config.yaml` and is loaded by `pipeline/config.py`. Steps run in order:

1. **`scripts/setup.sh`** — scaffolds the directory tree
2. **`pipeline/download/download_population_tables.py`** — downloads decennial census race/ethnicity counts (TOTPOP, WHITE, BLACK, POC, etc.) via Census API; uses IPUMS/NHGIS extracts for 1980 and 1990
3. **`pipeline/download/download_geographies.py`** — downloads TIGER/Line shapefiles (2000–2020 via Census API; 1980/1990 via IPUMS NHGIS)
4. **`pipeline/preprocessing/census_geographies.py`** — joins population tables to shapefiles, producing one attributed shapefile per state/year/level in `data/processed/census_geographies/`
5. **`pipeline/preprocessing/study_areas.py`** — builds study area boundary polygons (e.g. CBSA outlines from county-component `.xls` files) into `data/processed/study_area_definitions/`
6. **`pipeline/preprocessing/overlaps.py`** — clips census geography shapefiles to each study area boundary; outputs clipped shapefiles to `data/processed/clipped_geographies/`
7. **`pipeline/graphs.py`** — builds the dual adjacency graph from each clipped shapefile; drops zero-population nodes and ensures full connectivity; outputs `*_connected.json` files to `data/processed/dual_graphs/`
8. **`pipeline/metrics.py`** — computes ~80 segregation metrics per study area / year from each connected graph JSON; outputs one CSV row per area; errors logged to `outputs/<run>/metric_failures.csv`
9. **`pipeline/visualization/generate_figures.py`** — reads the metrics CSV and produces publication figures

## Configuration

All pipeline behavior is controlled by `pipeline/config.yaml`:

| Key | Example | Options |
|---|---|---|
| `study_area_type` | `cbsa` | `cbsa`, `max_city`, `max_county`, `county` |
| `census_geography_type` | `tracts` | `tracts`, `block_groups`, `blocks`, `counties` |
| `census_geography_years` | `[2020, 2010, 2000]` | list of years |
| `study_area_vintage` | `2020` | year |

For `study_area_type: cbsa`, a delineation file matching `list1_*<vintage>.xls` must exist in `data/raw/study_area_sources/`. A Census API key and IPUMS API key are required for downloads.

## Important directories

| Directory | Contents |
|---|---|
| `data/raw/study_area_sources/` | CBSA delineation `.xls` files (required input) |
| `data/raw/geographies/` | Raw downloaded TIGER/NHGIS shapefiles |
| `data/raw/population/` | Raw downloaded population CSV tables |
| `data/processed/census_geographies/` | Population-attributed shapefiles per state/year/level |
| `data/processed/study_area_definitions/` | Study area boundary `.gpkg` + metadata `.json` |
| `data/processed/clipped_geographies/` | Census units clipped to each study area |
| `data/processed/dual_graphs/` | Adjacency graph JSONs (`*_connected.json`) |
| `outputs/<run_name>/` | Metric CSVs, `metric_failures.csv`, figures, `run.log` |

## Important commands

All scripts use Typer and accept `--help`. Run from the repo root.

```bash
# Full reproduction
bash scripts/setup.sh
bash scripts/reproduce.sh

# Download
poetry run python pipeline/download/download_population_tables.py --level tracts --years "2020 2010 2000"
poetry run python pipeline/download/download_geographies.py --level tracts --years "2020 2010 2000"

# Preprocessing
poetry run python pipeline/preprocessing/census_geographies.py --level tracts --years "2020 2010 2000"
poetry run python pipeline/preprocessing/study_areas.py --filename data/raw/study_area_sources/list1_march_2020.xls --study-area-type cbsa
poetry run python pipeline/preprocessing/overlaps.py \
    "data/processed/study_area_definitions/cbsa_*_march_2020.gpkg" \
    data/processed/clipped_geographies \
    --census-geography-type tracts \
    --census-geography-years "2020 2010 2000" \
    --definition-vintage march_2020

# Graphs and metrics
poetry run python pipeline/graphs.py \
    "data/processed/clipped_geographies/*/tracts_in_cbsa_*_march_2020_vintage.gpkg"
poetry run python pipeline/metrics.py \
    "data/processed/dual_graphs/*/tracts_in_cbsa_*_march_2020_vintage_connected.json" \
    BLACK WHITE TOTPOP outputs/tracts_in_cbsa/white_black.csv

# Figures
poetry run python pipeline/visualization/generate_figures.py \
    --filename outputs/tracts_in_cbsa/white_black.csv \
    --prefix white_black_cbsa_tracts \
    --geography-type tracts \
    --study-area-type cbsa
```

## Testing / Verification

- Run `pytest` to execute the test suite under `pipeline/tests/`
- Run `bash scripts/reproduce.sh` only when full reproduction is needed

## Outputs

- Metric CSVs: `outputs/<run_name>/white_black.csv`, `outputs/<run_name>/white_poc.csv`
- Run log: `outputs/<run_name>/run.log`
- Figures: `outputs/<run_name>/figures/`
- Output formats must not change.