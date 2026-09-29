# Pipeline code

For installation, credentials, the Delaware example, national runs, and troubleshooting, use the
[main README](../README.md). It contains the complete operational walkthrough. The
[commented configuration](configs/example.yaml) documents individual run settings.

## Entry points

Run commands from the repository root with its locked environment:

```bash
uv run --locked python code/reproduce.py --help
```

- [`reproduce.py`](reproduce.py) runs all six stages by default, or selected positional stage names
  in pipeline order. Unselected prerequisites must already exist.
- [`record_raw_checksums.py`](record_raw_checksums.py) records diagnostic hashes of selected raw
  files separately from retrieval.
- [`repackage_graphs.py`](repackage_graphs.py) repackages existing graph ZIPs without rebuilding
  their graphs. See the [archive guide](../documentation/national_pipeline/05_graph_construction.md#archive-parts-and-repackaging).

## Follow a stage

Each stage guide explains its inputs, outputs, checks, rerun behavior, and internal responsibilities.

| Stage | Implementation entry point | Method guide |
| --- | --- | --- |
| Retrieve | [`retrieve_raw_data()`](national_pipeline/retrieve_data/retrieve_files.py) | [Sources and retrieval](../documentation/national_pipeline/01_raw_source_acquisition.md) |
| Process population | [`process_population_tables()`](national_pipeline/process_population/process_tables.py) | [Population tables](../documentation/national_pipeline/02_population_processing.md) |
| Join geographies | [`join_geography_tables()`](national_pipeline/join_geographies/join_tables.py) | [Geographic joins](../documentation/national_pipeline/03_geography_population_joining.md) |
| Assign study areas | [`assign_study_areas()`](national_pipeline/assign_study_areas/run_assignment.py) | [Study areas](../documentation/national_pipeline/04_study_area_assignment.md) |
| Build graphs | [`build_graph_archives()`](national_pipeline/build_graphs/run_build.py) | [Graph construction](../documentation/national_pipeline/05_graph_construction.md) |
| Compute metrics | [`compute_metrics()`](national_pipeline/compute_metrics/run_metrics.py) | [Metrics](../documentation/national_pipeline/06_metric_computation.md) |

Shared configuration lives in [`national_pipeline/pipeline_config.py`](national_pipeline/pipeline_config.py).
Source URLs, Census variables, and NHGIS table selections live beside their request builders under
[`national_pipeline/retrieve_data/`](national_pipeline/retrieve_data/). Change YAML to select
supported inputs; change the Python definitions to alter source products or variables.

## Use metrics independently

[`capy_metrics/`](capy_metrics/) supplies reusable array, matrix, and graph functions. It does not
own study selections or result tables; those belong to `national_pipeline/compute_metrics/`.
The [public-function examples](../documentation/national_pipeline/06_metric_computation.md#use-individual-metric-functions)
show both interfaces. For a script outside `code/`, put that directory on the import path:

```bash
PYTHONPATH=code uv run --locked python your_analysis.py
```

## Checks and archived code

```bash
uv run --locked python -m pytest
```

The root project selects [`tests/`](tests/). [`archive/`](archive/) contains an older implementation,
experiments, and separate environment files; it is outside the current test and lint configuration.
