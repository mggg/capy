# Capy

A replication pipeline for Census population and geographic data, study-area assignments, dual
graphs, and residential segregation metrics.

The pipeline covers raw-source retrieval through graph construction and metric computation for
1980–2020. See the [assignment guide](documentation/national_pipeline/04_study_area_assignment.md)
for study-area selection and the [metric
guide](documentation/national_pipeline/06_metric_computation.md) for score definitions. The
[data-decisions guide](documentation/national_pipeline/data_processing_decisions_and_anomalies.md)
collects the choices and source anomalies that shape the results. National analyses live in
[`code/national_figures/`](code/national_figures/). The [figure guide](documentation/figures.md)
explains their commands and separate LaTeX-ready outputs. Final publication verification remains
separate work.

## Run

Use Python 3.11 or newer, excluding 3.14.1, and install the locked environment:

```bash
uv sync --locked
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml
```

The small example retrieves 2020 Delaware inputs, processes their population tables, joins counts to
boundaries, assigns tracts to county study areas, and saves connected graphs and metric tables. To
select individual stages or configure the full run, credentials, offline retrieval, and reuse of
existing files, see the [run guide](code/README.md). [Source
documentation](documentation/national_pipeline/01_raw_source_acquisition.md) describes coverage,
provenance, and validation limits.

## Organization

- `code/`: executable workflows, reusable computation, configuration, and tests.
- `data/`: raw inputs, processed data, and finalized graph archives.
- `results/`: pipeline metrics, national figure tables, and experiment results.
- `figures/`: publication figures.
- `documentation/`: source and method documentation.

Raw inputs and working outputs are ignored by Git. Finalized graph ZIP archives will be tracked.

## Check

```bash
uv run --locked python -m pytest
```
