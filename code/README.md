# Run and understand the replication pipeline

The pipeline implements raw-data retrieval, population processing, boundary–population joins,
study-area assignment, graph construction, and metric computation for 1980–2020. Use the links
below to run it, understand the inputs, or follow the code.

Reusable score functions live in [`capy_metrics/`](capy_metrics/). Use their array or graph
interfaces to calculate individual metrics without running the pipeline; the
[metric guide](../documentation/metric_computation.md#use-individual-metric-functions) shows both.
[`capy_core/`](capy_core/) owns the pipeline stages, including archive loading, study-specific
metric choices, and result tables in `compute_metrics/`.

| What you want to do                                             | Where to start                                                                                                                                                           |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Install the environment and run a small example                 | [Repository README](../README.md#run)                                                                                                                                    |
| Choose years, geography levels, and data folders                | [Commented example configuration](configs/example.yaml)                                                                                                                  |
| Understand the Census variable codes and population definitions | [Population variable guide](../documentation/raw_source_acquisition.md#census-population-variable-guide)                                                                 |
| Find data sources and geographic coverage limits                | [Sources and coverage](../documentation/raw_source_acquisition.md#sources-and-coverage)                                                                                  |
| Find official API documentation and where requests are made     | [API reference](../documentation/raw_source_acquisition.md#api-documentation-and-request-addresses)                                                                      |
| Reuse downloaded files or resume retrieval                      | [Run instructions below](#run-retrieval) and [reusing local files](../documentation/raw_source_acquisition.md#reusing-local-files)                                       |
| Follow execution or change which tables are requested           | [Code walkthrough](../documentation/raw_source_acquisition.md#following-the-code) and [input definitions](../documentation/raw_source_acquisition.md#editing-raw-inputs) |
| Process downloaded population tables                            | [Population processing](../documentation/population_processing.md)                                                                                                       |
| Join boundaries and inspect unmatched records                   | [Geography joining](../documentation/geography_population_joining.md)                                                                                                    |
| Define study areas and select their Census units                | [Study-area assignment](../documentation/study_area_assignment.md)                                                                                                       |
| Build and read connected graph archives                         | [Graph construction](../documentation/graph_construction.md)                                                                                                             |
| Calculate segregation scores and fixed-sample yearly means      | [Metric computation](../documentation/metric_computation.md)                                                                                                             |

## Run the pipeline

`reproduce.py` runs all six implemented stages when no stage names are supplied:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml
```

To run only selected stages, give their names as positional arguments:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml \
    process-population join-geographies
```

Stages always run once in this order: `retrieve`, `process-population`, `join-geographies`,
`assign-study-areas`, `build-graphs`, `compute-metrics`. Unselected prerequisites are not run, so
their outputs must already exist. A failed stage or incomplete retrieval stops the pipeline before
subsequent stages. Use `--help` to see the stage descriptions. `--offline` overrides retrieval's
download setting; the other stages always read existing inputs. Checksum publication remains a
separate diagnostic command.

## Run retrieval

From the repository root, using the root project's locked environment:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml retrieve
uv run --locked python code/reproduce.py --config code/configs/replication.yaml retrieve
```

The first command downloads 2020 Delaware tract and county inputs, with population references; the
second requests the raw inputs for the paper's national CBSA analyses. For NHGIS downloads, supply
`IPUMS_API_KEY` in your shell or set `env_file: .env` in the YAML to load credentials from a file at
the repository root.
Census downloads require `CENSUS_API_KEY`. Existing environment variables take precedence over
values in the file. By default, `env_file: null` loads no file, and neither offline runs nor the
checksum command reads one.

Start with the commented [`configs/example.yaml`](configs/example.yaml) to make a custom run.
Choose geography levels and census years for both population and boundary data, plus the
study-area type and boundary year. The code adds the county and city inputs needed to define those
areas. [`configs/replication.yaml`](configs/replication.yaml) covers entire metropolitan areas
for the paper's national analyses. [`configs/max_city.yaml`](configs/max_city.yaml) uses the same
years and levels but selects one city per metro, adding the place inputs needed for city selection.
[`configs/county.yaml`](configs/county.yaml) covers individual counties, while
[`configs/max_county.yaml`](configs/max_county.yaml) selects the most populous county in each metro.
Both use the same years and levels as the paper configuration, with 2020 study-area definitions.
[`configs/small_example.yaml`](configs/small_example.yaml) selects Delaware tracts, their county
study-area definitions, and population references. The settings also control folders, download
workers, offline mode, and checksum output. Input definitions live alongside their retrieval code
in [`capy_core/retrieve_data/`](capy_core/retrieve_data/), grouped into `census/` and `nhgis/`
workflows. Configuration and temporary-file handling are shared under `capy_core/`.

The command calls `retrieve_raw_data(config, repository)` in
[`retrieve_files.py`](capy_core/retrieve_data/retrieve_files.py), which is also the entry point
for running retrieval from Python.

Unless absolute, top-level paths are relative to the repository root, while entries under
`raw_data_subdirectories` are relative to `raw_data_directory`. Filename selection patterns follow
that configured layout, as described in the
[retrieval guide](../documentation/raw_source_acquisition.md#configuring-paths), which also
explains command-line overrides.

Retrieval checks existing files before reusing them and downloads missing inputs, putting any
required 2010 county tables ahead of the block queries that depend on them. These
[basic checks](../documentation/raw_source_acquisition.md#basic-checks) cover file format and, for
NHGIS, any saved request. If a file fails, unrelated downloads continue.

In a terminal, active downloads show byte counts, speed, and an estimated completion time when the
size is known. The overall bar counts every processed file, including reused files and failed
requests, so reaching 100% does not establish that retrieval succeeded. Check the final status:
failed files or unfinished NHGIS extracts produce a nonzero exit status. When output is
redirected, the status messages remain and the bars are omitted.

If NHGIS is still preparing extracts after the initial downloads, the run uses their saved extract
numbers to recheck them every 60 seconds for up to 60 minutes. You can adjust this interval and
wait limit with `nhgis_retry_interval_seconds` and `nhgis_max_wait_minutes`, or set the latter to
zero to disable waiting. Each wait is capped by the time remaining, though the following retry
round, including its queued downloads, can finish past the limit. Any extracts left unfinished can
be resumed by rerunning the command, which also reuses completed files.

Ctrl-C stops waiting for NHGIS and cancels queued files during a download batch, allowing active
downloads to finish or fail before exit. Because submission records are saved, the next run can
resume those extracts.

Start with four download workers because higher concurrency can trigger rate limits;
`max_parallel_downloads` accepts any value of at least 1. When a server limits requests with HTTP
429, downloads retry up to three times, following a valid `Retry-After` header or waiting 30, 60,
then 120 seconds when none is supplied. Broken connections, timeouts, and incomplete transfers get
up to five whole-file attempts, each using a fresh temporary file, with waits of 2, 4, 8, then 10
seconds. Other HTTP errors, invalid selections, and file-format errors are reported as failures.
These transfer retries are separate from the NHGIS preparation checks described above.

To reuse data downloaded elsewhere, place it in the configured folders. You can check that the
selected files are available without downloading anything:

```bash
uv run --locked python code/reproduce.py --config code/configs/replication.yaml \
    --offline retrieve
```

See [raw-data retrieval](../documentation/raw_source_acquisition.md) for file locations, input
coverage, editing the Python input definitions, parallel Census/NHGIS workflows, and the separate
command used to publish diagnostic checksums. The sections below cover population processing,
geographic joins, study-area assignment, and graph construction.

Run checks with `uv run --locked python -m pytest`. Use one retrieval run per raw-data directory;
`max_parallel_downloads` controls parallel workers within that run.

## Process population tables

After retrieval, process the small example with:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml \
    process-population
```

Use `code/configs/replication.yaml` for all supported years and levels, or
`code/configs/modern_population.yaml` for only 2000–2020. The command reads existing inputs,
checks population counts, and saves Parquet tables beneath `processed_population_directory`. See
the [population-processing guide](../documentation/population_processing.md) for output fields,
checks, file locations, and rerun behavior.

## Join boundaries and populations

After population processing, attach counts to the selected boundaries:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml join-geographies
```

The command saves GeoParquet files, unmatched records, and population accounting beneath
`joined_geography_directory`. Use the same configuration for retrieval, population processing, and
joining. The [geography-joining guide](../documentation/geography_population_joining.md) explains
historical corrections, geometry repair, source limitations, and rerun behavior.

## Assign study areas

After geographic joining, construct definitions and select whole Census units inside them:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml assign-study-areas
```

The small example assigns Delaware tracts to its three counties. Metro modes use the March 2020
county roster; `max_city` ranks places by 2020 block population inside each metro. Outputs include
boundaries, candidate scores, unit memberships, and explicit empty or unavailable outcomes under
`study_area_directory`. See the [study-area guide](../documentation/study_area_assignment.md) for
selection rules, required inputs, and output interpretation. This command does not build graphs.

## Build graph archives

After assignment, build connected graphs and their population accounting:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml build-graphs
```

Each ZIP contains the selected year's graphs at one geography level, with removed-unit records and
summary accounting. Read graphs directly from these archives using `read_graph_from_archive()`; no
extraction step is needed. See the [graph guide](../documentation/graph_construction.md) for
filtering, connections, and examples. Set `max_parallel_graphs` in the YAML to control concurrent
graph builds and JSON writes; the national configurations use 28 workers.

## Compute metrics

Read the saved graph ZIPs and write per-area scores plus yearly averages:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml compute-metrics
```

No extraction or intermediate data files are required. The default output is
`results/metrics/county/2020/` for this example, with both White–Black and White–POC comparisons.
For individual scores on your own graphs or arrays, use the
[public metric functions](../documentation/metric_computation.md#use-individual-metric-functions).
Use `metric_names` to select formulas and `metric_results_directory` to change the output root.
The [metric guide](../documentation/metric_computation.md) explains the supported scores,
undefined values, population denominators, and the fixed sample used for each metric's yearly
means.
