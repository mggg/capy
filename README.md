# Capy

A replication pipeline for Census population and geographic data, study-area assignments, dual
graphs, and residential segregation metrics.

The pipeline covers raw-source retrieval through graph construction and metric computation for
1980–2020. See the [assignment guide](documentation/study_area_assignment.md) for study-area
selection and the [metric guide](documentation/metric_computation.md) for score definitions.
Experiment workflows, visualization, and final publication verification remain separate work.

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
documentation](documentation/raw_source_acquisition.md) describes coverage, provenance, and
validation limits.

## Organization

- `code/`: executable workflows, reusable computation, configuration, and tests.
- `data/`: raw inputs, processed data, and finalized graph archives.
- `results/`: numerical metric tables and averages.
- `figures/`: publication figures.
- `documentation/`: source and method documentation.
- `plans/`: implementation stages and acceptance criteria.

Raw inputs and working outputs are ignored by Git. Finalized graph ZIP archives will be tracked.

## Check

```bash
uv run --locked python -m pytest
```
