# Scripts

Shell scripts for running the pipeline and experiments.

## `reproduce.sh`

Runs the full pipeline end-to-end for a single configuration (census geography type, study area type, vintage). It:

1. Reads the run configuration via `capy_core/config.py` and exports environment variables.
2. Calls `setup.sh` to create the required folder structure.
3. Downloads and preprocesses census population tables and geographies (including a separate download for the study-area-definition geography if it differs from the census geography).
4. Builds study area definitions and spatial overlaps between census geographies and study areas.
5. Constructs dual graphs from the clipped geographies.
6. Computes segregation metrics (White–Black and White–POC) and saves CSVs to the run output directory.
7. Generates figures for both metric sets via `experiment_code/baseline/visualization/line_plots/generate_figures.py`.

Run from the project root:
```bash
bash scripts/reproduce.sh
```

## `run_experiment.sh`

Runs an experiment via the orchestration script. Accepts an optional path to a JSON config file (defaults to `experiment_code/baseline/config.json`).

```bash
bash scripts/run_experiment.sh                              # uses default config
bash scripts/run_experiment.sh experiment_code/my/config.json
```

## `setup.sh`

Creates the full `data/` folder structure expected by the pipeline — raw inputs (geographies, population tables, IPUMS extracts), processed intermediates (clipped geographies, dual graphs, study area definitions), and output directories. Called automatically by `reproduce.sh`, but can also be run standalone before a manual pipeline run.

```bash
bash scripts/setup.sh
```
