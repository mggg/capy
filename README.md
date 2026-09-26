# Capy

A replication pipeline for Census population and geographic data, study-area assignments, dual
graphs, and residential segregation metrics.

Raw-source retrieval and population processing for 1980–2020 are implemented. Geographic joins,
study-area assignment, and graph construction follow in the [pipeline plan](plans/pipeline.md).

## Run

Use Python 3.11 or newer, excluding 3.14.1, and install the locked environment:

```bash
uv sync --locked
uv run --locked python code/reproduce.py --config code/configs/small_example.yaml
```

The small example retrieves 2020 Delaware tract populations and boundaries. For the complete input
collection, credentials, offline retrieval, and reuse of existing files, see the
[run guide](code/README.md). [Source documentation](documentation/raw_source_acquisition.md)
describes coverage, provenance, and validation limits.

## Organization

- `code/`: executable workflows, reusable computation, configuration, and tests.
- `data/`: raw inputs, processed data, and finalized graph archives.
- `figures/`: publication figures.
- `documentation/`: source and method documentation.
- `plans/`: implementation stages and acceptance criteria.

Raw inputs and working outputs are ignored by Git. Finalized graph ZIP archives will be tracked.

## Check

```bash
uv run --locked python -m pytest
```
