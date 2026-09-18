# capy_core

Core pipeline modules for downloading data, preprocessing geographies, building graphs, and computing segregation metrics.

## Modules

| File | Purpose |
|---|---|
| `config.py` | Loads `config.yaml` and resolves derived config values. Prints shell `export` statements when run directly (used by `reproduce.sh`). |
| `graphs.py` | Builds dual adjacency graphs from clipped geography `.gpkg` files. Drops zero-population nodes and connects isolated components. Writes `*_orig.json` and `*_connected.json` pairs. |
| `metrics.py` | Computes ~80 segregation metrics per study area / year from connected graph JSONs (skew, edge, half-edge, Moran's I, dissimilarity, Gini, etc.). Outputs one CSV row per area. |
| `process_results.py` | Enriches a raw metrics CSV with study area metadata (title, area code, 2020 population) by reading the corresponding definition JSONs. |

## Subfolders

| Folder | Contents |
|---|---|
| `download/` | Scripts that fetch raw data from the Census API, Census TIGER FTP, and IPUMS/NHGIS. |
| `preprocessing/` | Scripts that transform raw downloads into population-attributed shapefiles, study area boundaries, and clipped census geography files. |
| `utils/` | Shared data model (`StudyArea`) and pipeline logging helpers. |
| `tests/` | Pytest test suite covering all core modules. |

## Graph outputs

`preprocessing/overlaps.py` selects each census unit whose representative point falls within a study-area boundary. `graphs.py` first writes that selection's geographic adjacency graph as `_orig.json`. It then removes nodes whose combined Black and White population is zero and connects any remaining components by adding edges between the nearest component geometries. The resulting `_connected.json` graph is the input to `metrics.py`. Removed units are recorded under `data/shared/outputs/<geography>_in_<study_area>/dropped_nodes/`.

See the [preprocessing guide](preprocessing/README.md) for the stage order, commands, and output paths.

## Configuration — `config.yaml`

All pipeline behaviour is controlled by `config.yaml`. To change a run, edit the values in that file before calling `reproduce.sh`. Environment variables do not override the YAML settings.

| Key | Description | Valid values |
|---|---|---|
| `study_area_type` | The geographic unit that defines each study area. | `cbsa`, `county`, `max_city`, `max_county` |
| `census_geography_type` | The census unit used as graph nodes. | `tracts`, `block_groups`, `blocks`, `counties` |
| `census_geography_years` | List of decennial census years to process. | `1980`, `1990`, `2000`, `2010`, `2020` |
| `study_area_vintage` | The delineation year for study area boundaries. | e.g. `2020` |

For `study_area_type: cbsa`, `max_city`, or `max_county`, a CBSA delineation file matching `list1_*<vintage>.xls` must exist in `data/shared/raw/study_area_sources/`.

> **Note:** 1980 is automatically skipped for `block_groups` and `blocks` because NHGIS does not publish 1980 block-group or block boundary shapefiles.
