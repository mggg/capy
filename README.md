## Project Purpose

This project downloads population and geography data from the Census Bureau API and IPUMS/NHGIS, constructs adjacency graphs where census units (e.g. tracts) within study areas (e.g. CBSAs) are connected if they share a border, and applies a battery of residential segregation metrics. The goal is to assess segregation and disagreement among metrics across geographies and decades.

## Folder structure

```
capy-bara/
├── data/
│   ├── raw/                        # downloaded source files (gitignored)
│   │   ├── geographies/            # TIGER/Line and NHGIS shapefiles
│   │   ├── population/             # Census API / NHGIS population tables
│   │   └── study_area_sources/     # CBSA delineation .xls files
│   └── processed/                  # pipeline intermediates (gitignored)
│       ├── census_geographies/     # population-attributed shapefiles per year/level
│       ├── study_area_definitions/ # study area boundary .gpkg + metadata .json
│       ├── clipped_geographies/    # census units clipped to each study area
│       ├── dual_graphs/            # adjacency graph JSONs per study area
│       └── dropped_nodes/          # zero-population nodes removed from graphs
│
├── outputs/                        # pipeline run outputs (gitignored)
│   ├── tracts_in_cbsa/             # metrics CSVs + figures for this configuration
│   ├── block_groups_in_cbsa/
│   └── cross_level_comparisons/    # figures comparing results across runs
│
├── pipeline/                       # core pipeline modules
│   ├── config.py                   # config loader; prints shell exports when run directly
│   ├── config.yaml                 # pipeline configuration
│   ├── graphs.py                   # dual adjacency graph construction
│   ├── metrics.py                  # segregation metric calculations
│   ├── process_results.py          # enriches metrics CSV with study area metadata
│   ├── download/                   # download_geographies.py, download_population_tables.py
│   ├── preprocessing/              # census_geographies.py, study_areas.py, overlaps.py
│   ├── visualization/              # generate_figures.py
│   └── utils/                      # definitions.py, pipeline_log.py
│
├── experiments/                    # hypothesis-testing experiments
│   └── <name>/                     # one folder per experiment
│
├── scripts/                        # shell scripts
│   ├── reproduce.sh                # full pipeline orchestration
│   └── setup.sh                    # scaffolds directory tree
│
└── archive/                        # inactive code and old outputs
```

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
9. **`pipeline/process_results.py`** — enriches the metrics CSV with study area metadata (title, population) from the definition JSON files
10. **`pipeline/visualization/generate_figures.py`** — reads the metrics CSV and produces publication figures

## Configuration

All pipeline behavior is controlled by `pipeline/config.yaml`:

| Key | Example | Options |
|---|---|---|
| `study_area_type` | `cbsa` | `cbsa`, `max_city`, `max_county`, `county` |
| `census_geography_type` | `tracts` | `tracts`, `block_groups`, `blocks`, `counties` |
| `census_geography_years` | `[2020, 2010, 2000]` | list of years |
| `study_area_vintage` | `2020` | year |

For `study_area_type: cbsa`, a delineation file matching `list1_*<vintage>.xls` must exist in `data/raw/study_area_sources/`. A Census API key and IPUMS API key are required for downloads.

## Running the pipeline

```bash
# scaffold directories, then run everything
bash scripts/setup.sh
bash scripts/reproduce.sh
```

The full run can take from a few minutes to many hours, depending on what level of geography you choose. Each step can also be run standalone, see below.

## Pipeline scripts

Run from the repo root with `poetry run python`.

### `pipeline/config.py`
Prints shell export statements derived from `pipeline/config.yaml`. Used internally by `reproduce.sh`; useful for inspecting resolved config values.
```bash
poetry run python pipeline/config.py
```

### `pipeline/download/download_population_tables.py`
Downloads decennial census population tables (race, ethnicity, total) for a given geography level and set of years.
```bash
poetry run python pipeline/download/download_population_tables.py \
    --level tracts \
    --years "2020 2010 2000"
```

### `pipeline/download/download_geographies.py`
Downloads TIGER/Line shapefiles (2000–2020) or IPUMS/NHGIS shapefiles (1980–1990) for a given geography level.
```bash
poetry run python pipeline/download/download_geographies.py \
    --level tracts \
    --years "2020 2010 2000"
```

### `pipeline/preprocessing/census_geographies.py`
Joins downloaded population tables to shapefiles, writing one `.gpkg` per state/year into `data/processed/census_geographies/`.
```bash
poetry run python pipeline/preprocessing/census_geographies.py \
    --level tracts \
    --years "2020 2010 2000"
```

### `pipeline/preprocessing/study_areas.py`
Builds study area boundary files (`.gpkg` + `.json`) from the CBSA definition Excel file. One file pair per study area in `data/processed/study_area_definitions/`.
```bash
poetry run python pipeline/preprocessing/study_areas.py \
    --filename data/raw/study_area_sources/list1_march_2020.xls \
    --study-area-type cbsa
```

### `pipeline/preprocessing/overlaps.py`
Clips census geography units to each study area boundary. Writes one `.gpkg` per study area and year to the output directory.
```bash
poetry run python pipeline/preprocessing/overlaps.py \
    "data/processed/study_area_definitions/cbsa_*_march_2020.gpkg" \
    data/processed/clipped_geographies \
    --census-geography-type tracts \
    --census-geography-years "2020 2010 2000" \
    --definition-vintage march_2020
```

### `pipeline/graphs.py`
Builds dual adjacency graphs from clipped shapefiles. Drops zero-population nodes and adds edges between any disconnected components. Writes `*_connected.json` files to `data/processed/dual_graphs/`.
```bash
poetry run python pipeline/graphs.py \
    "data/processed/clipped_geographies/*/tracts_in_cbsa_*_march_2020_vintage.gpkg"
```

### `pipeline/metrics.py`
Computes segregation metrics for each study area from connected graph JSONs. Arguments are the glob pattern, group columns, and output CSV path.
```bash
poetry run python pipeline/metrics.py \
    "data/processed/dual_graphs/*/tracts_in_cbsa_*_march_2020_vintage_connected.json" \
    BLACK WHITE TOTPOP \
    outputs/tracts_in_cbsa/white_black.csv
```

### `pipeline/visualization/generate_figures.py`
Reads a metrics CSV and writes figures to `outputs/<run>/figures/`.
```bash
poetry run python pipeline/visualization/generate_figures.py \
    --filename outputs/tracts_in_cbsa/white_black.csv \
    --prefix white_black_cbsa_tracts \
    --geography-type tracts \
    --study-area-type cbsa
```

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
