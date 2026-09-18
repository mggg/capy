## Project Purpose

This project downloads population and geography data from the Census Bureau API and IPUMS/NHGIS, constructs adjacency graphs where census units (e.g. tracts) within study areas (e.g. CBSAs) are connected if they share a border, and applies a battery of residential segregation metrics. The goal is to assess segregation and disagreement among metrics across geographies and decades.

## Workflow map

| Task | Instructions |
|---|---|
| Install dependencies and configure a run | [Quick start](#quick-start) and [Configuration](#configuration) |
| Download and prepare data, build graphs, and calculate metrics | [Pipeline overview](#pipeline-overview) and [Pipeline scripts](#pipeline-scripts) |
| Generate baseline figures and appendix tables | [`experiment_code/baseline/README.md`](experiment_code/baseline/README.md) |
| Run the Iowa experiment | [`experiment_code/iowa_scripts/README.md`](experiment_code/iowa_scripts/README.md) |
| Run the synthetic-grid experiment | [`experiment_code/grid_figs_scripts/README.md`](experiment_code/grid_figs_scripts/README.md) |
| Run the assortativity-grid experiment | [`experiment_code/assortativity_grids/README.md`](experiment_code/assortativity_grids/README.md) |
| Run the observed-diffusion experiment | [`experiment_code/observed_diffusion/README.md`](experiment_code/observed_diffusion/README.md) |

## Quick start

There are two main ways to use this repo:

- **Mode 1 — Core pipeline:** download Census data, build adjacency graphs, and compute segregation metrics from scratch.
- **Mode 2 — Experiments:** run separate metrics-related experiments. Experiments have their own READMEs under `experiment_code/<name>/` and some can use supplied data without running the full pipeline. Supplied baseline metric CSVs still require locally generated study-area metadata; see the [baseline guide](experiment_code/baseline/README.md#using-supplied-metric-csvs).

Both modes require installing dependencies first:

```bash
make install   # install Python dependencies via Poetry
make setup     # scaffold the data directory tree
```

### Mode 1: Core pipeline

#### Credentials

A Census API and/or NHGIS key is required for runs, depending on run configurations. An IPUMS API key is required only when downloading 1980 or 1990 data (those decades use NHGIS instead of the Census API). NHGIS also requires a free account registration at [uma.pop.umn.edu/nhgis/registration/new](https://uma.pop.umn.edu/nhgis/registration/new). Census API is needed to download 2000-2020 data.

Keys can be set as shell environment variables or in a `.env` file at the repo root. The `.env` parser expects bare `KEY=value` lines — do not use an `export` prefix.

```bash
# shell environment
export CENSUS_API_KEY="your_census_key"
export IPUMS_API_KEY="your_ipums_key"   # only needed for 1980/1990
```

```
# .env file at repo root — no "export" prefix
CENSUS_API_KEY=your_census_key
IPUMS_API_KEY=your_ipums_key
```

#### Running

Set your run configuration in `capy_core/config.yaml`, then run:

```bash
make run        # equivalent to: bash scripts/reproduce.sh
```

This downloads data, builds graphs, computes metrics, and generates baseline figures in one pass. See [Pipeline overview](#pipeline-overview) for the full step-by-step breakdown.

### Mode 2: Experiments

Each experiment lives under `experiment_code/<name>/` and has its own README with the command sequence:

| Experiment | README |
|---|---|
| Baseline figures and tables | [`experiment_code/baseline/README.md`](experiment_code/baseline/README.md) |
| Iowa | [`experiment_code/iowa_scripts/README.md`](experiment_code/iowa_scripts/README.md) |
| Synthetic grids | [`experiment_code/grid_figs_scripts/README.md`](experiment_code/grid_figs_scripts/README.md) |
| Assortativity grids | [`experiment_code/assortativity_grids/README.md`](experiment_code/assortativity_grids/README.md) |
| Observed diffusion | [`experiment_code/observed_diffusion/README.md`](experiment_code/observed_diffusion/README.md) |

## Folder structure

```
capy-bara/
├── data/
│   ├── shared/
│   │   ├── raw/                        # downloaded source files (gitignored)
│   │   │   ├── geographies/            # TIGER/Line and NHGIS shapefiles
│   │   │   ├── population/             # Census API / NHGIS population tables
│   │   │   └── study_area_sources/     # CBSA delineation .xls files
│   │   ├── processed/                  # pipeline intermediates (gitignored)
│   │   │   ├── census_geographies/     # population-attributed shapefiles per year/level
│   │   │   ├── study_area_definitions/ # study area boundary .gpkg + metadata .json
│   │   │   ├── clipped_geographies/    # census units clipped to each study area
│   │   │   └── dual_graphs/            # adjacency graph JSONs per study area
│   │   └── outputs/                    # supplied metric CSVs and generated run outputs
│   │       ├── tracts_in_cbsa/         # metrics CSVs for this configuration
│   │       ├── tracts_in_max_city/
│   │       ├── block_groups_in_cbsa/
│   │       └── ...                     # one folder per geography/study-area combination
│   └── experiment_specific/
│       ├── ia_files/                   # supplied Iowa graph JSON
│       └── observed_diffusion_data/    # supplied cluster membership and metric CSVs
│
├── figures/                            # output figures (gitignored)
│   ├── baseline/                       # line plots and rankings per run configuration
│   ├── Iowa/
│   ├── assortativity_grids/
│   └── observed_diffusion/
│
├── capy_core/                          # core pipeline modules
│   ├── config.py                       # config loader; prints shell exports when run directly
│   ├── config.yaml                     # pipeline configuration
│   ├── graphs.py                       # dual adjacency graph construction
│   ├── metrics.py                      # segregation metric calculations
│   ├── process_results.py              # enriches metrics CSV with study area metadata
│   ├── download/                       # download_geographies.py, download_population_tables.py
│   ├── preprocessing/                  # census_geographies.py, study_areas.py, overlaps.py
│   ├── utils/                          # definitions.py, pipeline_log.py
│   └── tests/                          # pytest test suite
│
├── experiment_code/                    # hypothesis-testing experiments
│   ├── visualization_settings.py       # shared plot styling
│   ├── baseline/visualization/         # line plots, rho plots, lambda rankings
│   ├── iowa_scripts/                   # Iowa map and isolation plots
│   ├── grid_figs_scripts/              # synthetic grid figure scripts
│   ├── assortativity_grids/            # assortativity simulation and plots
│   └── observed_diffusion/             # cluster backprojection and radial plots
│
├── scripts/                            # shell scripts
│   ├── reproduce.sh                    # full pipeline orchestration
│   └── setup.sh                        # scaffolds directory tree
│
├── stats/                              # summary statistics
└── archive/                            # inactive code and old outputs
```

## Pipeline overview

The full pipeline is driven by `scripts/reproduce.sh`. Configuration lives in `capy_core/config.yaml` and is loaded by `capy_core/config.py`. Steps run in order:

1. **`scripts/setup.sh`** — scaffolds the directory tree
2. **`capy_core/download/download_population_tables.py`** — downloads decennial census race/ethnicity counts (TOTPOP, WHITE, BLACK, POC, etc.) via Census API; uses IPUMS/NHGIS extracts for 1980 and 1990
3. **`capy_core/download/download_geographies.py`** — downloads TIGER/Line shapefiles (2000–2020 via Census API; 1980/1990 via IPUMS NHGIS)
4. **`capy_core/preprocessing/census_geographies.py`** — joins population tables to shapefiles, producing one attributed shapefile per state/year/level in `data/shared/processed/census_geographies/`
5. **`capy_core/preprocessing/study_areas.py`** — builds study area boundary polygons (e.g. CBSA outlines from county-component `.xls` files) into `data/shared/processed/study_area_definitions/`
6. **`capy_core/preprocessing/overlaps.py`** — clips census geography shapefiles to each study area boundary; outputs clipped shapefiles to `data/shared/processed/clipped_geographies/`
7. **`capy_core/graphs.py`** — builds the dual adjacency graph from each clipped shapefile; drops zero-population nodes and ensures full connectivity; outputs `*_connected.json` files to `data/shared/processed/dual_graphs/`
8. **`capy_core/metrics.py`** — computes ~80 segregation metrics per study area / year from each connected graph JSON; outputs one CSV row per area; errors logged to `data/shared/outputs/<run>/metric_failures.csv`
9. **`capy_core/process_results.py`** — enriches the metrics CSV with study area metadata (title, population) from the definition JSON files
10. **`experiment_code/baseline/visualization/line_plots/generate_figures.py`** — reads the metrics CSV and writes publication figures under `figures/baseline/<run>/`

## Configuration

All pipeline behavior is controlled by `capy_core/config.yaml`:

| Key | Example | Options |
|---|---|---|
| `study_area_type` | `cbsa` | `cbsa`, `max_city`, `max_county`, `county` |
| `census_geography_type` | `tracts` | `tracts`, `block_groups`, `blocks`, `counties` |
| `census_geography_years` | `[2020, 2010, 2000]` | list of years |
| `study_area_vintage` | `2020` | year |

To change the run configuration, edit `capy_core/config.yaml` directly. Environment variables do not override YAML values. For `study_area_type: cbsa`, a delineation file matching `list1_*<vintage>.xls` must exist in `data/shared/raw/study_area_sources/`.

## Running the pipeline

```bash
# scaffold directories, then run everything
bash scripts/setup.sh
bash scripts/reproduce.sh
```

The full run can take from a few minutes to many hours, depending on what level of geography you choose. Each step can also be run standalone, see below.

## Worked example: 2020 tracts within CBSAs

This example builds tract adjacency graphs for every 2020 CBSA, calculates White–Black and White–POC segregation metrics, and generates the baseline figures. It uses only 2020 data, so it requires a Census API key but does not require an IPUMS API key or NHGIS extract.

First, install the dependencies and configure `CENSUS_API_KEY` in the shell or a repository-root `.env` file as described under [Credentials](#credentials).

```bash
make install
```

CBSA boundaries are defined by their component counties. Download the Census Bureau's March 2020 delineation spreadsheet before running the setup or pipeline commands:

```bash
mkdir -p data/shared/raw/study_area_sources
curl --fail --location \
    https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2020/delineation-files/list1_2020.xls \
    --output data/shared/raw/study_area_sources/list1_march_2020.xls
```

The local name `list1_march_2020.xls` gives the definitions the vintage label `march_2020`. That label appears in the generated boundary, clipped-geography, and graph filenames.

Set `capy_core/config.yaml` to:

```yaml
study_area_type: cbsa
census_geography_type: tracts
census_geography_years:
  - 2020
study_area_vintage: 2020
```

Then run the complete pipeline:

```bash
make run
```

The run downloads and processes two types of geography. Tracts become the graph nodes, while counties are downloaded separately and dissolved to create the CBSA boundaries. The stages then select tracts within each CBSA, build adjacency graphs, calculate both sets of metrics, and generate figures.

The main intermediate and final outputs are:

| Output | Location |
|---|---|
| CBSA boundaries and metadata | `data/shared/processed/study_area_definitions/cbsa_*_march_2020.{gpkg,json}` |
| Tracts selected within each CBSA | `data/shared/processed/clipped_geographies/2020/tracts_in_cbsa_*_march_2020_vintage.gpkg` |
| Original adjacency graphs | `data/shared/processed/dual_graphs/2020/tracts_in_cbsa_*_march_2020_vintage_orig.json` |
| Connected graphs used for metrics | `data/shared/processed/dual_graphs/2020/tracts_in_cbsa_*_march_2020_vintage_connected.json` |
| Metric CSVs and run log | `data/shared/outputs/tracts_in_cbsa/` |
| Baseline figures | `figures/baseline/tracts_in_cbsa/` |

The `_orig.json` files preserve the geographic adjacency graph. To create `_connected.json`, graph construction removes tracts with zero combined Black and White population and adds edges between otherwise disconnected components. Metric calculations use the connected graphs. If the run reports failed metric calculations, inspect `data/shared/outputs/tracts_in_cbsa/metric_failures.csv` together with `run.log`; successful rows remain in the metric CSVs.

To extend this example to 1980 or 1990, add those years to `census_geography_years` and configure the IPUMS API key and NHGIS account described under [Credentials](#credentials).

## Pipeline scripts

Run from the repo root with `poetry run python`.

### `capy_core/config.py`
Prints shell export statements derived from `capy_core/config.yaml`. Used internally by `reproduce.sh`; useful for inspecting resolved config values.
```bash
poetry run python capy_core/config.py
```

### `capy_core/download/download_population_tables.py`
Downloads decennial census population tables (race, ethnicity, total) for a given geography level and set of years.
```bash
poetry run python capy_core/download/download_population_tables.py \
    --level tracts \
    --years "2020 2010 2000"
```

### `capy_core/download/download_geographies.py`
Downloads TIGER/Line shapefiles (2000–2020) or IPUMS/NHGIS shapefiles (1980–1990) for a given geography level.
```bash
poetry run python capy_core/download/download_geographies.py \
    --level tracts \
    --years "2020 2010 2000"
```

### `capy_core/preprocessing/census_geographies.py`
Joins downloaded population tables to shapefiles, writing one `.gpkg` per state/year into `data/shared/processed/census_geographies/`.
```bash
poetry run python capy_core/preprocessing/census_geographies.py \
    --level tracts \
    --years "2020 2010 2000"
```

### `capy_core/preprocessing/study_areas.py`
Builds study area boundary files (`.gpkg` + `.json`) from the CBSA definition Excel file. One file pair per study area in `data/shared/processed/study_area_definitions/`.
```bash
poetry run python capy_core/preprocessing/study_areas.py \
    --filename data/shared/raw/study_area_sources/list1_march_2020.xls \
    --study-area-type cbsa
```

### `capy_core/preprocessing/overlaps.py`
Clips census geography units to each study area boundary. Writes one `.gpkg` per study area and year to the output directory.
```bash
poetry run python capy_core/preprocessing/overlaps.py \
    "data/shared/processed/study_area_definitions/cbsa_*_march_2020.gpkg" \
    data/shared/processed/clipped_geographies \
    --census-geography-type tracts \
    --census-geography-years "2020 2010 2000" \
    --definition-vintage march_2020
```

### `capy_core/graphs.py`
Builds dual adjacency graphs from clipped shapefiles. Drops zero-population nodes and adds edges between any disconnected components. Writes `*_connected.json` files to `data/shared/processed/dual_graphs/`.
```bash
poetry run python capy_core/graphs.py \
    "data/shared/processed/clipped_geographies/*/tracts_in_cbsa_*_march_2020_vintage.gpkg"
```

### `capy_core/metrics.py`
Computes segregation metrics for each study area from connected graph JSONs. Arguments are the glob pattern, group columns, and output CSV path.
```bash
poetry run python capy_core/metrics.py \
    "data/shared/processed/dual_graphs/*/tracts_in_cbsa_*_march_2020_vintage_connected.json" \
    BLACK WHITE TOTPOP \
    data/shared/outputs/tracts_in_cbsa/white_black.csv
```

### `experiment_code/baseline/visualization/line_plots/generate_figures.py`
Reads a metrics CSV and writes figures to `figures/baseline/<run>/`.
```bash
poetry run python experiment_code/baseline/visualization/line_plots/generate_figures.py \
    --filename data/shared/outputs/tracts_in_cbsa/white_black.csv \
    --prefix white_black \
    --geography-type tracts \
    --study-area-type cbsa
```

## Dependencies

Python deps are managed via Poetry. See `pyproject.toml` for the full list.

```bash
pip install poetry
make install # equivalent to: poetry install
poetry shell # activate the Poetry environment
```
