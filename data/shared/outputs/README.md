# data/shared/outputs

Final outputs of each pipeline run, organised by configuration. Each subfolder is named `<census_geography_type>_in_<study_area_type>` (e.g. `tracts_in_cbsa`).

Several metric CSVs are supplied in the repository. They contain raw metric results but not the study-area metadata used by baseline plots. Plotting them requires the matching, locally generated definition JSONs under `data/shared/processed/study_area_definitions/`; see the [baseline experiment guide](../../../experiment_code/baseline/README.md#using-supplied-metric-csvs).

| File / subfolder | Contents |
|---|---|
| `white_black.csv` | Metrics CSV for the White–Black group pair, one row per study area × year. |
| `white_poc.csv` | Metrics CSV for the White–POC group pair. |
| `run.log` | Full log from the pipeline run that produced this folder. |
| `metric_failures.csv` | Study areas for which metric computation failed (e.g. single-tract cities with zero-edge graphs). |
| `dropped_nodes/` | `.gpkg` files of zero-population nodes removed during graph construction, one per census year. |

Publication figures and LaTeX tables generated from these metrics are written under `figures/baseline/<census_geography_type>_in_<study_area_type>/`. See the [baseline experiment guide](../../../experiment_code/baseline/README.md) for the commands.
