# capy_core/utils

Shared utilities used across the pipeline.

## Modules

### `definitions.py`

Pydantic data model for a study area.

`StudyArea` holds the fields written to each `data/shared/processed/study_area_definitions/*.json` file and read back by `process_results.py`:

| Field | Type | Description |
|---|---|---|
| `area_code` | `str` | CBSA code, FIPS county code, or Census place GEOID. |
| `area_title` | `str` | Human-readable name (e.g. `"New York-Newark-Jersey City, NY-NJ-PA"`). |
| `component_counties_fips` | `list[str]` | 5-digit FIPS codes of all component counties. |
| `total_population` | `int \| None` | Total population summed across component counties (2020). |
| `geometry` | `GeoDataFrame \| None` | Boundary polygon; excluded when serialising to JSON. |

### `pipeline_log.py`

Thin logging helpers for pipeline scripts.

- **`log(msg)`** — prints *msg* with immediate flush; a drop-in replacement for `print()` in pipeline scripts.
- **`tqdm_file`** — file handle to pass as `file=` to every `tqdm` call so that progress bars go to the terminal even when stdout is captured by the pipeline log tee redirect. Falls back to `None` (tqdm default → stderr) when no controlling terminal is available.
