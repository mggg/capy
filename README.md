# Capy

Capy is a replication pipeline for Census population and geographic data, study-area assignments,
connected geographic graphs, and residential segregation metrics from 1980 through 2020. It
retrieves the source files, checks and processes population counts, matches counts to boundaries,
selects Census units inside study areas, builds graphs, and calculates per-area scores and yearly
averages.

This guide walks through installation, a small Delaware example, and the national analyses. The
six-stage pipeline currently ends at metric tables. Experiment workflows, figure generation, and
final verification against publication results are separate work; see
[publication status](#publication-status).

## Contents

- [Set up the repository](#set-up-the-repository)
- [Configure data access](#configure-data-access)
- [Run the small example](#run)
- [Work through the six stages](#work-through-the-six-stages)
- [Run the national analyses](#run-the-national-analyses)
- [Customize a run](#customize-a-run)
- [Resume, rerun, or work offline](#resume-rerun-or-work-offline)
- [Read and interpret the results](#read-and-interpret-the-results)
- [Troubleshooting](#troubleshooting)
- [Record inputs and check the code](#record-inputs-and-check-the-code)
- [Publication status](#publication-status)
- [Repository and method guides](#repository-and-method-guides)

## Set up the repository

You need Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), internet access for
installation and source retrieval, and writable storage for the data and results. The project
supports Python 3.11 or newer, excluding 3.14.1 and Python 4. The commands below use Python 3.13
explicitly; uv can [install that interpreter](https://docs.astral.sh/uv/guides/install-python/)
for you.

If you do not already have a checkout:

```bash
git clone https://github.com/mggg/capy.git
cd capy
```

For replication, use the repository revision associated with the analysis you intend to reproduce.
The commands in this guide describe this checkout. If you already have it, open a terminal in its
root directory, the directory containing `pyproject.toml`, `uv.lock`, and this README.

Install uv using its platform-specific instructions above. Then create the locked environment:

```bash
uv python install 3.13
uv sync --locked --python 3.13
uv run --locked python --version
uv run --locked python code/reproduce.py --help
```

`uv sync` creates `.venv/` and installs the dependencies recorded in `uv.lock`, including the
geospatial libraries and development tools. `--locked` checks that the lockfile matches the
project without updating it. Keep both `pyproject.toml` and `uv.lock` from the same repository
revision. There is no need to activate the environment when using `uv run`.

**Run all commands below from the repository root.** The current pipeline uses the root Python
environment. The environment files and setup scripts in `code/archive/` belong to an older
implementation.

Start with the Delaware example before allocating resources for a national run. National block
inputs, joined polygons, and temporary graph files can require substantial disk and memory. This
repository does not specify a measured minimum disk capacity or a guaranteed runtime. Allow space
for raw inputs, derived tables, and graph-packaging scratch files together; the size of the final
ZIPs is not the peak storage requirement.

## Configure data access

The pipeline downloads modern population tables from the Census API, boundaries from Census and
NHGIS, and supporting population and metro-membership references. Credentials are required when
the corresponding API download is needed:

| Credential       | How to obtain it                                                                                                                     | When needed                                                                 |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| `CENSUS_API_KEY` | [Request a Census API key](https://api.census.gov/data/key_signup.html) and complete its activation.                                 | Census population downloads, including the Delaware example.                |
| `IPUMS_API_KEY`  | Register for NHGIS access and create a key using the [IPUMS account instructions](https://developer.ipums.org/docs/v1/get-started/). | NHGIS extracts, including historical inputs in the national configurations. |

Export the keys in the terminal that will launch the pipeline, replacing the placeholders:

```bash
export CENSUS_API_KEY='your-census-key'
export IPUMS_API_KEY='your-ipums-key'
```

For the small example, only `CENSUS_API_KEY` is needed. Alternatively, create a `.env` file at the
repository root with the applicable entries:

```dotenv
CENSUS_API_KEY=your-census-key
IPUMS_API_KEY=your-ipums-key
```

Then change this setting in the configuration you will run:

```yaml
env_file: .env
```

The supplied configurations use `env_file: null`, so merely creating `.env` does not load it.
Existing shell variables take precedence over values in the file. `.env` is ignored by Git; keep
credentials out of the YAML. Offline retrieval and checksum recording do not read the env file.
Processing existing data and computing metrics from graph archives do not need API keys.

## Run

The [small-example configuration](code/configs/small_example.yaml) selects 2020 Delaware tracts,
the county inputs that define its three study areas, and the population references used for
validation. After setup and credentials, run all six stages:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml
```

The stages run in this order:

```text
retrieve → process-population → join-geographies → assign-study-areas
         → build-graphs → compute-metrics
```

A failed stage stops the command before later stages run. Incomplete retrieval, including NHGIS
extracts that are still pending, also stops the pipeline with a nonzero exit status. At the end of
a successful run, the terminal reports metric computation complete, with counts of defined and
undefined values.

With the configuration's default paths, look for:

| Output                                                               | What to check                                      |
| -------------------------------------------------------------------- | -------------------------------------------------- |
| `data/processed/population/processing_summary.csv`                   | Population tables and their validation totals.     |
| `data/processed/geography/join_summary.csv`                          | Matched and unmatched population accounting.       |
| `data/processed/study_areas/county/2020/summary.parquet`             | Outcomes for the three county study areas.         |
| `data/graphs/county_2020_2020_tracts_part01.zip`                     | Connected county graphs and their accounting.      |
| `results/metrics/county/2020/2020_tracts.parquet`                    | Per-county scores for both population comparisons. |
| `results/metrics/county/2020/average_when_all_years_present.parquet` | Means over the example's selected areas and year.  |

Older unnumbered graph ZIPs are also readable. The graph stage repackages them into numbered parts
when reusing them. A file's presence alone does not establish that the entire run succeeded; check
the command's completion status and stage summaries.

If you want to inspect each intermediate result, use the individual commands in the next section
instead of the all-stage command. Running both repeats the processing work.

## Work through the six stages

Use the **same configuration** across stages. You can select several stages in one invocation:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml \
    process-population join-geographies
```

Selected stages run once in pipeline order, regardless of their order on the command line.
**Unselected prerequisites are not run automatically.** The example above requires retrieved
inputs already on disk. Only retrieval accesses data providers; subsequent stages read local
files.

### 1. Retrieve source files

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml retrieve
```

Retrieval saves inputs beneath `data/raw/`, checks existing files before reusing them, and
downloads missing inputs. For Delaware, the selected files include Census tract and county
population JSON, TIGER tract and county boundary ZIPs, and state population references. Keep the
downloaded archives in their configured locations; manual extraction is unnecessary.

Check for `Retrieval complete`. The progress bar counts processed files, including failures, so
100% alone does not mean success. Failed files are reported individually. For a national run,
NHGIS may need time to prepare extracts: saved submission records let a later invocation resume
without submitting the same request again. Keep `data/raw/saved_nhgis_requests/` with the raw
data.

The [source guide](documentation/national_pipeline/01_raw_source_acquisition.md) explains exact
file layouts, requested variables, coverage, and the basic checks performed before reuse.

### 2. Process population tables

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml \
    process-population
```

Processing validates counts and geographic identifiers, compares totals with state and published
references, and writes Parquet tables. The Delaware tract table is
`data/processed/population/2020/tracts/DE_2020_populations.parquet`; county and state reference
tables are also saved. `processing_summary.csv` is written after every selected table succeeds.

The derived population columns are `TOTPOP`, `WHITE`, `BLACK`, and `POC`. `WHITE` and `BLACK` are
non-Hispanic White-alone and Black-alone counts, and `POC = TOTPOP - WHITE`. Source fields and row
locations are retained for tracing counts. See the
[population guide](documentation/national_pipeline/02_population_processing.md) for historical
derivations and the limits of validation.

### 3. Join population to boundaries

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml join-geographies
```

This stage matches geographic identifiers, repairs invalid geometry, and applies documented
historical corrections. For each selected state/year/level, it writes three files beneath
`data/processed/geography/`, for example:

```text
2020/tracts/DE_2020_geography.parquet
2020/tracts/DE_2020_unmatched_population.parquet
2020/tracts/DE_2020_unmatched_boundaries.parquet
```

Read `join_summary.csv` for input, matched, and unmatched counts, and `geometry_repairs.csv` for
geometry repair records. Unmatched files are written even when empty. An unmatched boundary does
not imply zero population: historical exclusions and missing matches remain explicit. The
[joining guide](documentation/national_pipeline/03_geography_population_joining.md) explains the
accounting and source corrections.

### 4. Assign Census units to study areas

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml assign-study-areas
```

Assignment constructs study-area boundaries at the configured definition vintage, then selects
whole Census units whose polygon representative points are covered by each area. It keeps each
selected polygon and its full population; it does not clip units or prorate residents.

The Delaware outputs live in `data/processed/study_areas/county/2020/`. Inspect
`definitions.parquet` for the county definitions, `memberships/2020/tracts/` for unit memberships,
and `summary.parquet` for area outcomes. A `ready` outcome means units were selected;
`no_units_selected` means no representative point qualified. Historical coverage that is
unavailable is recorded separately, with unknown counts rather than zeros.

See the [assignment guide](documentation/national_pipeline/04_study_area_assignment.md) for metro
membership, city/county ranking, ties, and the full output schema.

### 5. Build connected graph archives

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml build-graphs
```

Graph construction retains units with `WHITE + BLACK > 0`, builds rook adjacency, and connects
separate components with explicitly marked artificial edges. A corner contact alone is not rook
adjacency. Both population comparisons subsequently use this same filtered graph.

Archives are named by study-area type, definition vintage, node year, and node level, for example
`county_2020_2020_tracts_part01.zip`. Each numbered part is a standalone ZIP containing whole area
graphs, removed-unit records, and `summary.csv`. Keep all parts for a selection together. Read the
summary to inspect graph status, node/edge counts, and retained/removed populations. Graphs do not
need to be extracted before metric computation.

Completed selections are reused on reruns. After changing polygon shapes or graph methods, set
`rebuild_graphs: true` before rebuilding; archive reuse does not detect every such change. The
[graph guide](documentation/national_pipeline/05_graph_construction.md) covers archive readers,
artificial connections, parallelism, and repackaging older archives.

### 6. Compute metrics

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml compute-metrics
```

This stage needs only the selected graph ZIPs. It computes the configured metrics for each area,
then writes per-year/level score tables, `graph_outcomes.parquet`, and
`average_when_all_years_present.parquet`. The Delaware output folder is
`results/metrics/county/2020/`.

The defaults include evenness, Capy, Moran, and assortativity metrics for both `white_black` and
`white_poc`. Some scores can be mathematically undefined; their rows have null values and explicit
reasons. These are distinct from missing or malformed archives, which stop the run. See
[reading results](#read-and-interpret-the-results) below and the
[metric guide](documentation/national_pipeline/06_metric_computation.md) for formulas and
conventions.

## Run the national analyses

After completing the small example, choose the study-area configuration you need:

| Configuration                                                   | Scope                                                                                       |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| [`replication.yaml`](code/configs/replication.yaml)             | Entire metropolitan areas (`cbsa`), with March 2020 county membership and 2020 definitions. |
| [`max_city.yaml`](code/configs/max_city.yaml)                   | The most populous city within each metro, ranked by its population inside that metro.       |
| [`max_county.yaml`](code/configs/max_county.yaml)               | The most populous county in each metro.                                                     |
| [`county.yaml`](code/configs/county.yaml)                       | Individual counties.                                                                        |
| [`modern_population.yaml`](code/configs/modern_population.yaml) | All supported levels for 2000–2020, plus inputs for 2020 city selection.                    |
| [`example.yaml`](code/configs/example.yaml)                     | Commented customization example: 1990–2020 tracts with maximum-city study areas.            |

The first four configurations request counties, tracts, block groups, and blocks for 1980–2020.
Supported node combinations are:

| Census year            | Counties | Tracts/BNAs                 | Block groups | Blocks      |
| ---------------------- | -------- | --------------------------- | ------------ | ----------- |
| 1980                   | Yes      | Partial historical coverage | Unavailable  | Unavailable |
| 1990, 2000, 2010, 2020 | Yes      | Yes                         | Yes          | Yes         |

Unsupported 1980 block and block-group combinations are omitted. Historical sources cover the 50
states and DC, excluding Puerto Rico; modern source coverage and historical exclusions are
detailed in the
[source guide](documentation/national_pipeline/01_raw_source_acquisition.md#sources-and-coverage).
A completed pipeline does not imply complete historical geographic coverage.

For the national CBSA analysis, run:

```bash
uv run --locked python code/reproduce.py --config code/configs/replication.yaml
```

For the maximum-city analysis, use a separate invocation:

```bash
uv run --locked python code/reproduce.py --config code/configs/max_city.yaml
```

These configurations share raw, population, and joined-geography folders, allowing raw downloads
to be reused. Run them sequentially when sharing those folders. Study-area outputs and metric
results are separated by type/vintage, while graph filenames include that identity. The national
CBSA metric tables live in `results/metrics/cbsa/2020/`; maximum-city tables live in
`results/metrics/max_city/2020/`.

To calculate scores from existing graph archives, you can skip all earlier stages:

```bash
uv run --locked python code/reproduce.py --config code/configs/replication.yaml compute-metrics
```

This requires every selected archive part, but no raw or processed inputs and no API credentials.
It replaces the corresponding metric tables, so use a separate results root to retain a previous
run for comparison.

### Resource controls

`max_parallel_downloads` controls retrieval workers; the national configurations use 4. Increasing
it can trigger provider rate limits. `max_parallel_graphs` independently controls concurrent area
graph builds and defaults to 4; use 1 to build sequentially with less concurrent memory demand.
Population processing and metric computation do not become parallel by increasing either setting.

The two inverse-distance Moran variants compare every pair of nodes, so their work grows
quadratically with graph size. They can dominate metric runtime on large block graphs. To explore
a smaller selection, copy a configuration and narrow `metric_names`, years, or levels. Such a run
produces only the selected analyses; preserve all requested metrics when reproducing a full
result.

## Customize a run

Copy the commented example and edit the copy:

```bash
cp code/configs/example.yaml code/configs/my_run.yaml
```

The main choices are:

| Setting                   | Effect                                                                               |
| ------------------------- | ------------------------------------------------------------------------------------ |
| `census_geography_years`  | Population/boundary years used for graph nodes: 1980, 1990, 2000, 2010, 2020.        |
| `census_geography_levels` | Node resolution: `counties`, `tracts`, `block_groups`, `blocks`.                     |
| `study_area_type`         | Enclosing areas: `county`, `cbsa`, `max_county`, `max_city`.                         |
| `study_area_vintage`      | Boundary/population year defining the enclosing areas, held fixed across node years. |
| `population_comparisons`  | `white_black`, `white_poc`, or both.                                                 |
| `metric_names`            | The formulas to calculate; accepted names are listed in `example.yaml`.              |

For example, these settings select county study areas with tract nodes in two decades:

```yaml
census_geography_years: [2010, 2020]
census_geography_levels: [tracts]
study_area_type: county
study_area_vintage: 2020
population_comparisons: [white_black, white_poc]
metric_names: [dissimilarity, capy, moran_row_standardized]
file_path_patterns: ["*"]
```

Apply those settings to your copied configuration, then run:

```bash
uv run --locked python code/reproduce.py --config code/configs/my_run.yaml
```

Node year and definition vintage serve different purposes. A 2010 tract graph within a 2020 county
uses 2010 tract populations and boundaries selected against the 2020 county definition. Metro
modes always use the March 2020 membership workbook, even with a historical definition vintage.
`max_city` supports only vintage 2020 and adds county, place, and block inputs for city ranking,
even when graph nodes are tracts from other years.

### Paths and separate runs

Top-level configured paths are relative to the **repository root**, not the YAML's directory.
Absolute paths work too, allowing data to live on another drive. The defaults are:

```yaml
raw_data_directory: data/raw
processed_population_directory: data/processed/population
joined_geography_directory: data/processed/geography
study_area_directory: data/processed/study_areas
graph_archive_directory: data/graphs
metric_results_directory: results/metrics
```

Keep these stage folders separate, with no output folder containing or sitting inside an input
folder. Entries under `raw_data_subdirectories` are relative to `raw_data_directory`. Changing a
path changes where the pipeline looks; it does not move existing files. The `--config` argument
itself is resolved from the shell's current directory.

To keep separate analyses of the same area type/vintage, give them separate output roots. This is
particularly important for assignment and metrics, whose reruns replace that type/vintage's
outputs, including years removed from the new configuration. Different YAML filenames alone do not
isolate their outputs.

### Restricting raw files

Leave `file_path_patterns: ["*"]` for a complete configured run. This setting filters requested
file paths, not study-area IDs, and can remove prerequisites that later stages need. The Delaware
example includes a coordinated set of population, boundary, and reference filenames; it is a
starting point for partial **county-mode** runs. Metro modes require the complete metro roster's
inputs. Changing only a state code in a filter is not sufficient to create a partial metro run.

For custom input layouts and filters, follow the
[retrieval guide](documentation/national_pipeline/01_raw_source_acquisition.md#configuring-paths).

## Resume, rerun, or work offline

After a retrieval failure or a pending extract, rerun the same retrieval command. Completed files
are reused after their basic checks, and saved NHGIS request numbers are reused for pending
extracts. By default, retrieval rechecks pending extracts every 60 seconds for up to 60 minutes
following the initial batches. Configure `nhgis_retry_interval_seconds` and
`nhgis_max_wait_minutes` to change this; a zero-minute limit disables that wait.

After fixing a later-stage failure, restart at that stage and list the remaining stages. For
example, if joining failed after population processing succeeded:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml \
    join-geographies assign-study-areas build-graphs compute-metrics
```

Rerun behavior differs by stage:

| Stage                | Existing outputs                                                                                                     |
| -------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `retrieve`           | Reuses files that pass basic checks; resumes saved NHGIS submissions.                                                |
| `process-population` | Replaces selected population outputs and rewrites the processing summary.                                            |
| `join-geographies`   | Replaces selected joins/unmatched files and rewrites join summaries.                                                 |
| `assign-study-areas` | Replaces definitions, memberships, and accounting for the selected type/vintage.                                     |
| `build-graphs`       | Reuses completed year/level selections after inventory/accounting checks; rebuilds missing or incomplete selections. |
| `compute-metrics`    | Replaces all Parquet result tables for the selected type/vintage.                                                    |

Derived-stage files are published individually. A failed run can leave some newly completed
outputs without final summary tables. Fix the reported cause and rerun the stage; do not interpret
an incomplete folder as a completed analysis.

If you change upstream data or processing, rerun the affected stage and all dependent stages. When
existing graphs must change, use `rebuild_graphs: true`, then restore it to `false` after the
intentional rebuild. If only formulas or metric selection change, rerunning `compute-metrics` is
sufficient. Keep inputs and source code stable while a run is active.

To check that raw inputs are available without accessing data providers:

```bash
uv run --locked python code/reproduce.py --config code/configs/replication.yaml --offline retrieve
```

To run all stages using existing raw inputs:

```bash
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml --offline
```

`--offline` overrides the retrieval setting only; it does not fetch missing files or disable
validation. It also does not control uv's dependency access, so install the environment before
working without a network connection. When moving data between machines, preserve the configured
raw-data layout and saved NHGIS records.

## Read and interpret the results

Read the example's scores and averages with pandas from the repository root:

```bash
uv run --locked python - <<'PY'
from pathlib import Path
import pandas as pd

results_directory = Path("results/metrics/county/2020")
scores = pd.read_parquet(results_directory / "2020_tracts.parquet")
means = pd.read_parquet(results_directory / "average_when_all_years_present.parquet")

print(scores.head(12).to_string(index=False))
print(scores["undefined_reason"].value_counts(dropna=False).to_string())
print(means.to_string(index=False))
PY
```

Each score row identifies its study area, Census year, geography level, population comparison,
metric, value, graph status, and any undefined reason. `graph_outcomes.parquet` provides archive
filenames and population accounting. Read boundary or definition GeoParquet files with
`geopandas.read_parquet()` to retain their geometry and coordinate system.

Interpret these outputs with the following constraints:

- **Means use a fixed sample.** Each metric/comparison/resolution includes only areas with a
  defined score in every selected supported year. Means weight areas equally, not by population.
  Changing the selected years can therefore change the cohort and the means for years shared by
  both runs.
- **Null does not mean zero.** Inspect `undefined_reason` and `graph_status`. Constant unit
  shares, absent groups, unavailable historical coverage, or no selected units can make scores
  undefined.
- **Both comparisons use the White–Black-filtered graph.** Removing units with zero
  White-plus-Black population can remove other residents from White–POC analysis. Archive
  accounting records them.
- **Spatial scores include artificial connections.** These edges make the graph connected and
  participate in adjacency-based metrics alongside geographic neighbors.
- **Source coverage matters.** In particular, 1980 tract/BNA coverage is partial. Population
  checks, geographic exclusions, and graph filtering describe different limits; inspect their
  respective summaries rather than treating a final score as proof of complete coverage.
- **Population totals overlap.** Do not add counts across years, resolutions, overlapping areas,
  or overlapping population groups as though they were disjoint residents.

The [metric guide](documentation/national_pipeline/06_metric_computation.md) defines every score,
its weights, undefined conditions, and output schema. For independent analyses, it also shows how
to use the public `capy_metrics` functions on arrays or graphs. Those examples need `code/` on
Python's import path, for example `PYTHONPATH=code uv run --locked python your_analysis.py`.

## Troubleshooting

| Symptom                                       | What to do                                                                                                                                        |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `uv` is not found                             | Complete the uv installation and open a terminal where its executable is on `PATH`.                                                               |
| Import errors or incompatible dependencies    | Run `uv sync --locked --python 3.13` from the root and launch commands with `uv run --locked`. Check that you are using the root environment.     |
| Missing API key                               | Export the named key in the launching shell, or set `env_file: .env` in the actual YAML being used.                                               |
| Retrieval remains incomplete                  | Inspect the reported failed/pending files. Resolve failed requests, allow NHGIS preparation to finish, and rerun retrieval.                       |
| An existing raw file fails validation         | Inspect or move the affected file aside before retrying; retrieval never overwrites existing raw files, even when their checks fail.              |
| HTTP 429 or transfer failures                 | Retrieval has bounded retries. Lower `max_parallel_downloads` if rate limits persist, then rerun.                                                 |
| Missing population references or boundaries   | Rerun retrieval with the same configuration and check whether `file_path_patterns` excluded dependencies.                                         |
| Invalid config field or unsupported selection | Compare with `example.yaml`; unknown fields and empty required selections are rejected.                                                           |
| Population mismatch or unmatched geography    | Inspect the identified source and stage accounting. Use the method guides to distinguish documented exclusions from unexpected input differences. |
| Graph reuse rejects membership/accounting     | After verifying the intended upstream changes, rerun graph construction with `rebuild_graphs: true`.                                              |
| Missing numbered graph part                   | Restore the complete selection or rebuild it from completed upstream inputs. Do not combine parts from different runs.                            |
| High memory use during graph construction     | Reduce `max_parallel_graphs`; additional workers hold additional polygons and graphs in memory.                                                   |
| Slow block-level metric computation           | Check whether inverse-distance Moran scores dominate; use an explicitly smaller metric selection for exploratory runs.                            |

Ctrl-C during retrieval cancels queued work but can wait for active transfers to finish. Graph
construction similarly waits for running workers before cleanup. Allow that cleanup to complete,
then resume with the same configuration.

## Record inputs and check the code

Keep the configuration, repository revision, and `uv.lock` with your results. Record the current
revision with `git rev-parse HEAD`; also retain any local changes that affect the analysis.

After retrieval completes, you can record SHA-256 digests of the selected raw files:

```bash
uv run --locked python code/record_raw_checksums.py \
    --config code/configs/replication.yaml --output data/my_run_raw_checksums.sha256
```

The separate output filename preserves the supplied `data/raw_checksums.sha256` reference.
Checksum recording reads local bytes and creates a diagnostic manifest; retrieval does not compare
downloads against that manifest. Different bytes warrant investigation, but matching checksums
alone do not validate the study methods. See
[checksum documentation](documentation/national_pipeline/01_raw_source_acquisition.md#published-raw-checksums).

Run the current pipeline's tests with:

```bash
uv run --locked python -m pytest
```

The root configuration selects `code/tests/`, excluding archived tests. Passing tests checks the
implementation; it does not replace running the selected data pipeline and examining its
accounting.

## Publication status

The runnable entry point in this checkout is `code/reproduce.py`, ending at metric computation.
The [figure documentation](documentation/figures.md) describes a separate national figure
workflow, but its `code/run_experiment.py` and `code/make_figures.py` entry points are not present
in this checkout. Those commands are not part of the runnable walkthrough above.

Older experiments and visualization code remain under `code/archive/`. Their paths and environment
have not been adapted to the current pipeline. Completing the six stages produces graph archives
and metric tables; reproducing final publication figures additionally requires the applicable
experiment selection, plotting workflow, and verification against the published results.

## Repository and method guides

| Location                  | Purpose                                                                                    |
| ------------------------- | ------------------------------------------------------------------------------------------ |
| `code/reproduce.py`       | CLI for the six current stages.                                                            |
| `code/configs/`           | Run configurations, including the commented example.                                       |
| `code/national_pipeline/` | Retrieval, population processing, geography, assignment, graphs, and metric orchestration. |
| `code/capy_metrics/`      | Reusable metric functions independent of pipeline files.                                   |
| `code/tests/`             | Tests for the current implementation.                                                      |
| `code/archive/`           | Older reference implementation and experiments.                                            |
| `data/`                   | Raw inputs, processed intermediates, graph archives, and checksum records.                 |
| `results/`                | Numerical metric tables and averages.                                                      |
| `figures/`                | Publication figure destination.                                                            |
| `documentation/`          | Source, method, and interpretation guides.                                                 |

Raw inputs and processed intermediates are ignored by Git. Final graph ZIPs and existing metric
Parquet tables are versioned, so rerunning analyses can change tracked artifacts.

For detailed methods and code entry points, follow:

1. [Raw sources, coverage, variables, and file validation](documentation/national_pipeline/01_raw_source_acquisition.md).
2. [Population derivation and checks](documentation/national_pipeline/02_population_processing.md).
3. [Boundary matching, repairs, and unmatched records](documentation/national_pipeline/03_geography_population_joining.md).
4. [Study-area definitions and unit assignment](documentation/national_pipeline/04_study_area_assignment.md).
5. [Graph construction and archive format](documentation/national_pipeline/05_graph_construction.md).
6. [Metric formulas, public functions, and averages](documentation/national_pipeline/06_metric_computation.md).
7. [Data-processing decisions and anomalies](documentation/national_pipeline/data_processing_decisions_and_anomalies.md).

The [code guide](code/README.md) maps these responsibilities to their implementation entry points.
