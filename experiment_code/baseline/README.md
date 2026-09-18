# Baseline experiments

The baseline workflow calculates segregation metrics for Census geographies within a selected study-area type and then produces the paper's comparison figures and tables.

To produce data for these, configure the geography, study area, years, and study-area vintage in [`capy_core/config.yaml`](../../capy_core/config.yaml), then run the pipeline from the repository root:

```bash
bash scripts/reproduce.sh
```

[`scripts/reproduce.sh`](../../scripts/reproduce.sh) downloads and processes the required data, builds graphs, calculates metrics, and generates the baseline line plots. Metric CSVs are written under:

```text
data/shared/outputs/<geography>_in_<study_area>/
```

### Using supplied metric CSVs

The repository includes raw metric CSVs for several configurations under `data/shared/outputs/`. These CSVs do not contain the study-area names, codes, definition vintage, census year, or 2020 population required by the plotting scripts. The plotting scripts derive the year and vintage from each graph filename and load the names, codes, and population from matching JSON files under `data/shared/processed/study_area_definitions/`. Those JSON files are generated locally and are not supplied with the repository.

To plot a supplied metric CSV, first run the core pipeline through `capy_core/preprocessing/study_areas.py` for the CSV's study-area type and vintage. The [worked 2020 example](../../README.md#worked-example-2020-tracts-within-cbsas) shows the required source data and configuration. Running all of `scripts/reproduce.sh` also creates the metadata, but recalculates and replaces the metric CSVs. Once the definition JSONs exist, run the visualization commands directly to retain the supplied metric values.

See the [baseline visualization guide](visualization/README.md) for commands that generate the other figures and tables from those CSVs. Generated figure locations and their producing scripts are indexed in the [baseline figures README](../../figures/baseline/README.md).
