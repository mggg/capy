# Capy

Capy is a replication pipeline for studying residential segregation in Census population and
geographic data from 1980 through 2020. It retrieves source files, checks population counts,
matches counts to boundaries, assigns Census units to study areas, builds connected geographic
graphs, and calculates segregation scores. Separate workflows prepare national figures and tables
and run grid, diffusion, and geographic experiments.

Start with the Delaware example below to follow the complete pipeline on a small selection. The
[run guide](code/README.md) explains individual stages and reruns, while the
[commented configuration](code/configs/example.yaml) describes all run settings. Source
definitions, scientific choices, and validation limits live in the linked method guides.

## Contents

- [Set up the environment](#set-up-the-environment)
- [Configure data access](#configure-data-access)
- [Run the small example](#run)
- [Choose a national analysis](#choose-a-national-analysis)
- [Prepare figures and experiments](#prepare-figures-and-experiments)
- [Understand the results](#understand-the-results)
- [Repository organization and method guides](#repository-organization-and-method-guides)
- [Check the code](#check)

## Set up the environment

Use Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), and Python 3.11 or newer,
excluding Python 3.14.1 and Python 4. If you do not already have a checkout:

```bash
git clone https://github.com/mggg/capy.git
cd capy
```

Run the commands in this guide from the repository root, which contains `pyproject.toml` and
`uv.lock`. Install the locked environment and inspect the pipeline command:

```bash
uv sync --locked
uv run --locked python code/reproduce.py --help
```

`uv sync` creates the local `.venv/` environment. Keep `pyproject.toml` and `uv.lock` from the
same repository revision; `--locked` prevents installation from silently updating the dependency
lock. The environment files under `code/archive/` belong to the inactive implementation.

Source retrieval needs internet access and writable data directories. National block runs can
require substantial storage and memory because raw inputs, joined polygons, and temporary graph
files coexist. Start with the small example before scheduling a national run; the repository does
not specify a measured minimum capacity or guaranteed runtime.

## Configure data access

The Delaware example needs a Census API key when downloading population tables. Obtain one from
the [Census key signup page](https://api.census.gov/data/key_signup.html), activate it, and export
it in the terminal that will run the pipeline:

```bash
export CENSUS_API_KEY='your-census-key'
```

National runs also retrieve historical data from NHGIS. For those downloads, supply an IPUMS API
key for an account with NHGIS access:

```bash
export IPUMS_API_KEY='your-ipums-key'
```

Alternatively, put the applicable variables in a `.env` file at the repository root and set
`env_file: .env` in the YAML configuration you run. The supplied configurations use
`env_file: null`, so creating the file alone does not load it. Existing shell variables take
precedence. `.env` is ignored by Git; keep credentials out of run configurations. The
[retrieval guide](documentation/national_pipeline/01_raw_source_acquisition.md#api-documentation-and-request-addresses)
links to provider documentation and explains the requested data.

Only retrieval contacts data providers. Processing existing inputs and computing scores from saved
graph archives require no API keys.

## Run

The [small-example configuration](code/configs/small_example.yaml) selects 2020 Delaware tracts,
the three county study areas containing them, and the population references needed for validation.
Run all six stages with:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml
```

The scientific operations run in this order:

```text
retrieve → process-population → join-geographies → assign-study-areas
         → build-graphs → compute-metrics
```

A failed stage or incomplete retrieval stops the command before later stages run. Check the final
completion messages: a retrieval progress bar reaching 100% means every request was attempted, not
that every input is ready.

With the configuration's default paths, a successful run produces:

| Output                                                                   | What it contains                                                    |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| `data/processed/population/processing_summary.csv`                       | Population-table row counts, totals, and applied checks.            |
| `data/processed/geography/join_summary.csv`                              | Accounting for matched, unmatched, and excluded population records. |
| `data/processed/study_areas/county/2020/summary.parquet`                 | Census-unit assignment outcomes for the three counties.             |
| `data/graphs/county_2020_2020_tracts_part01.zip`                         | County graphs, removed-unit records, and graph accounting.          |
| `results/metrics/county/2020_tracts_COUNTY20_metrics.parquet`            | Per-county scores and reasons for undefined values.                 |
| `results/metrics/county/COUNTY20_average_when_all_years_present.parquet` | Yearly means and their contributing areas.                          |

To run selected stages, append their names. For example, once the raw inputs exist:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml \
    process-population join-geographies
```

Unselected prerequisites do not run automatically. Use the same configuration across stages so
input selections and paths agree. Most relative data paths start at the repository root, not at
the configuration file's directory; the commented configuration explains the exceptions.

Retrieval reuses files in their configured locations and resumes pending NHGIS extracts using
saved submission records. Later processing stages can replace derived outputs, so rerunning the
entire command is different from resuming only retrieval. See the
[run guide](code/README.md#run-the-pipeline) for stage commands, offline retrieval, and recovery.

## Choose a national analysis

The national configurations use 2020 study-area definitions and request all supported node years
and resolutions from 1980 through 2020:

| Configuration                                     | Study areas                                                     |
| ------------------------------------------------- | --------------------------------------------------------------- |
| [replication.yaml](code/configs/replication.yaml) | Entire metropolitan areas (`cbsa`).                             |
| [max_city.yaml](code/configs/max_city.yaml)       | One city per metro, ranked by its population inside that metro. |
| [max_county.yaml](code/configs/max_county.yaml)   | The most populous county in each metro.                         |
| [county.yaml](code/configs/county.yaml)           | Individual counties.                                            |

For the national CBSA pipeline, run:

```bash
uv run --locked python code/reproduce.py --config code/configs/replication.yaml
```

These configurations share input directories, so run them sequentially when using their default
paths. To customize years, geography levels, metrics, or folders, copy and edit
[example.yaml](code/configs/example.yaml). `max_parallel_downloads` and `max_parallel_graphs`
control retrieval and graph-building concurrency separately. Increasing either does not speed up
metric computation; the inverse-distance Moran scores can be particularly expensive on large block
graphs.

If the selected graph archives are already available, compute scores without retrieving or
processing the source data:

```bash
uv run --locked python code/reproduce.py --config code/configs/replication.yaml compute-metrics
```

Every selected numbered archive part must be present. This command replaces the corresponding
metric tables; choose another `metric_results_directory` to retain a separate run. See the
[metric guide](documentation/national_pipeline/06_metric_computation.md#saved-tables-and-yearly-averages)
for output names and replacement behavior.

## Prepare figures and experiments

Figure preparation and rendering are separate from the six-stage pipeline. Once the CBSA metric
outputs and study-area definitions exist, prepare national score histories and draw them with:

```bash
uv run --locked python code/run_experiment.py national --config code/configs/replication.yaml
uv run --locked python code/make_figures.py national --config code/configs/replication.yaml
```

Preparation saves analysis tables under `results/national/processed_data/`; rendering reads those
tables and writes images under `figures/national/`. Style changes therefore need only the
rendering command. Figure components are separate 300 dpi PNGs, with titles and axis labels left
for LaTeX assembly. The [national figure guide](documentation/figures.md) covers available plots,
publication tables, cohort selection, and file locations.

The [experiment guide](documentation/experiments.md) gives commands and input requirements for
grid arrangements, diffusion, Iowa county configurations, and neighborhood change. These workflows
also save computations separately from their figures.

## Understand the results

The study counts are `TOTPOP`, `WHITE`, `BLACK`, and `POC`. `WHITE` and `BLACK` count non-Hispanic
White-alone and Black-alone residents; `POC = TOTPOP - WHITE`. Both White–Black and White–POC
comparisons use graphs retaining only units with positive `WHITE + BLACK`. Removed units can still
contain other residents, whose counts remain in graph accounting. The
[graph guide](documentation/national_pipeline/05_graph_construction.md) explains this population
restriction and the added edges that connect disconnected components.

Historical coverage is incomplete: 1980 block and block-group boundaries are unavailable, and 1980
tracts do not cover every study area. Unmatched boundaries do not imply zero population. Read the
[data-decisions guide](documentation/national_pipeline/data_processing_decisions_and_anomalies.md)
for documented source corrections and unresolved geographic limitations.

A mathematically undefined score is saved as null with an explicit reason. Yearly averages use
areas with a defined score in every selected, supported year, separately for each metric,
population comparison, and resolution. Figure preparation applies its own documented cohort
restrictions. Successful pipeline execution establishes the implemented checks, not final
verification against every published figure or table.

## Repository organization and method guides

Maintained code lives under `code/`: `national_pipeline/` handles data preparation and metric
outputs, `capy_metrics/` provides reusable score functions, and `national_figures/` and
`experiments/` prepare analyses. `plotting/` contains shared drawing styles. Use the
[metric examples](documentation/national_pipeline/06_metric_computation.md#use-individual-metric-functions)
to calculate individual scores without running the pipeline.

Raw inputs and working artifacts are stored under `data/raw/` and `data/processed/` and are
ignored by Git. Final graph ZIPs under `data/graphs/` are versioned. Numerical outputs belong in
`results/`, figures in `figures/`, and source and method explanations in `documentation/`.
Inactive code lives in `code/archive/` outside the maintained checks.

| Stage                               | Method guide                                                                                       |
| ----------------------------------- | -------------------------------------------------------------------------------------------------- |
| Retrieve sources                    | [Raw-source acquisition](documentation/national_pipeline/01_raw_source_acquisition.md)             |
| Process counts                      | [Population processing](documentation/national_pipeline/02_population_processing.md)               |
| Match shapes and counts             | [Geography–population joining](documentation/national_pipeline/03_geography_population_joining.md) |
| Define study areas and select units | [Study-area assignment](documentation/national_pipeline/04_study_area_assignment.md)               |
| Construct connected graphs          | [Graph construction](documentation/national_pipeline/05_graph_construction.md)                     |
| Calculate scores                    | [Metric computation](documentation/national_pipeline/06_metric_computation.md)                     |

## Check

Run the maintained test suite from the repository root:

```bash
uv run --locked python -m pytest
```

Tests cover formulas, pipeline behavior, and small regression cases. They do not replace checking
the completeness and accounting of a particular national run or reconciling its results with the
publication.
