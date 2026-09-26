# Run and understand the replication pipeline

The pipeline implements raw-data retrieval and population processing for 1980–2020. Use the links
below to run it, understand the inputs, or follow the code, and consult the pipeline plan for the
later processing stages.

| What you want to do                                             | Where to start                                                                                                                                                           |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Install the environment and run a small example                 | [Repository README](../README.md#run)                                                                                                                                    |
| Choose years, geography levels, and data folders                | [Commented example configuration](configs/example.yaml)                                                                                                                  |
| Understand the Census variable codes and population definitions | [Population variable guide](../documentation/raw_source_acquisition.md#census-population-variable-guide)                                                                 |
| Find data sources and geographic coverage limits                | [Sources and coverage](../documentation/raw_source_acquisition.md#sources-and-coverage)                                                                                  |
| Find official API documentation and where requests are made     | [API reference](../documentation/raw_source_acquisition.md#api-documentation-and-request-addresses)                                                                      |
| Reuse downloaded files or resume retrieval                      | [Run instructions below](#run-retrieval) and [reusing local files](../documentation/raw_source_acquisition.md#reusing-local-files)                                        |
| Follow execution or change which tables are requested           | [Code walkthrough](../documentation/raw_source_acquisition.md#following-the-code) and [input definitions](../documentation/raw_source_acquisition.md#editing-raw-inputs) |
| Process downloaded population tables | [Population processing](../documentation/population_processing.md) |
| Understand the planned processing, study-area, and graph stages | [Pipeline plan](../plans/pipeline.md)                                                                                                                                    |

## Run retrieval

From the repository root, using the root project's locked environment:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml
uv run --locked python code/reproduce.py --config code/configs/replication.yaml
```

The first command downloads 2020 Delaware tract populations, boundaries, and population references;
the second requests the full collection of 1,275 raw files. For NHGIS downloads, supply
`IPUMS_API_KEY` in your shell or set `env_file: .env` in the YAML to load credentials from a file at
the repository root. Census requests also use `CENSUS_API_KEY` when supplied, and existing
environment variables take precedence over values in the file. By default, `env_file: null` loads no
file, and neither offline runs nor the checksum command reads one.

Start with the commented [`configs/example.yaml`](configs/example.yaml) to make a custom run. Choose
geography levels and census years for both population and boundary data, plus the study-area type
and boundary year. The code adds the county and city inputs needed to define those areas.
[`configs/replication.yaml`](configs/replication.yaml) requests the full collection;
[`configs/small_example.yaml`](configs/small_example.yaml) selects Delaware tracts and the
references needed to check their population. The settings also control folders, download workers,
offline mode, and checksum output. Input definitions live alongside their retrieval code in
[`capy_core/retrieve_data/`](capy_core/retrieve_data/), grouped into `census/` and `nhgis/`
workflows. Configuration and temporary-file handling are shared under `capy_core/`.

The command calls `retrieve_raw_data(config, repository)` in
[`retrieve_files.py`](capy_core/retrieve_data/retrieve_files.py), which is also the entry point for
running retrieval from Python.

Unless absolute, top-level paths are relative to the repository root, while entries under
`raw_data_subdirectories` are relative to `raw_data_directory`. Filename selection patterns follow
that configured layout, as described in the
[retrieval guide](../documentation/raw_source_acquisition.md#configuring-paths), which also explains
command-line overrides.

Retrieval checks existing files before reusing them and downloads missing inputs, putting any
required 2010 county tables ahead of the block queries that depend on them. These
[basic checks](../documentation/raw_source_acquisition.md#basic-checks) cover file format and, for
NHGIS, any saved request. If a file fails, unrelated downloads continue.

In a terminal, active downloads show byte counts, speed, and an estimated completion time when the
size is known. The overall bar counts every processed file, including reused files and failed
requests, so reaching 100% does not establish that retrieval succeeded. Check the final status:
failed files or unfinished NHGIS extracts produce a nonzero exit status. When output is redirected,
the status messages remain and the bars are omitted.

If NHGIS is still preparing extracts after the initial downloads, the run uses their saved extract
numbers to recheck them every 60 seconds for up to 60 minutes. You can adjust this interval and wait
limit with `nhgis_retry_interval_seconds` and `nhgis_max_wait_minutes`, or set the latter to zero to
disable waiting. Each wait is capped by the time remaining, though the following retry round,
including its queued downloads, can finish past the limit. Any extracts left unfinished can be
resumed by rerunning the command, which also reuses completed files.

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
    --offline
```

See [raw-data retrieval](../documentation/raw_source_acquisition.md) for file locations, input
coverage, editing the Python input definitions, parallel Census/NHGIS workflows, and the separate
command used to publish diagnostic checksums. Geographic joins, study-area assignment, and graph
construction follow the [pipeline plan](../plans/pipeline.md).

Run checks with `uv run --locked python -m pytest`. Use one retrieval run per raw-data directory;
`max_parallel_downloads` controls parallel workers within that run.

## Process population tables

After retrieval, process the small example with:

```bash
uv run --locked python code/process_population.py --config code/configs/small_example.yaml
```

Use `code/configs/replication.yaml` for all supported years and levels, or
`code/configs/modern_population.yaml` for only 2000–2020. The command reads existing inputs, checks
population counts, and saves Parquet tables beneath `processed_population_directory`. See the
[population-processing guide](../documentation/population_processing.md) for output fields, checks,
file locations, and rerun behavior.
