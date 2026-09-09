# capy_core/preprocessing

Scripts that transform raw downloads into the intermediate files consumed by `graphs.py`. They run in the order listed below.

## Scripts

### `census_geographies.py`

Joins population tables to TIGER/NHGIS boundary shapefiles, producing one population-attributed `.gpkg` per state / year. Output goes to `data/shared/processed/census_geographies/<level>/`.

- Reads population CSVs from `data/shared/raw/population/` and shapefiles from `data/shared/raw/geographies/`.
- Matches rows by a zero-padded FIPS JOIN_KEY (state + county + tract, etc.).
- Reprojects all outputs to USA Contiguous Albers Equal Area (esri:102003).

```bash
poetry run python capy_core/preprocessing/census_geographies.py \
    --level tracts \
    --years "2020 2010 2000"
```

### `study_areas.py`

Builds study area boundary files (`.gpkg` + `.json`, one pair per study area) from the CBSA delineation Excel file and the census geography files produced above. Output goes to `data/shared/processed/study_area_definitions/`.

Four `study_area_type` modes are supported:

| Mode | Definition |
|---|---|
| `cbsa` | Dissolved union of all component counties for each CBSA. |
| `county` | One file per individual county. |
| `max_county` | The most populous component county within each CBSA. |
| `max_city` | The most populous Census place whose geometry intersects the CBSA boundary. |

```bash
poetry run python capy_core/preprocessing/study_areas.py \
    --filename data/shared/raw/study_area_sources/list1_march_2020.xls \
    --study-area-type cbsa
```

### `overlaps.py`

Clips census geography units to each study area boundary, selecting units whose representative point falls within the study area polygon. Output goes to `data/shared/processed/clipped_geographies/<year>/`, one `.gpkg` per study area.

Uses a bounding-box spatial index to avoid loading state files that cannot possibly intersect a given study area, making it practical even for block-level runs.

```bash
poetry run python capy_core/preprocessing/overlaps.py \
    "data/shared/processed/study_area_definitions/cbsa_*_march_2020.gpkg" \
    data/shared/processed/clipped_geographies \
    --census-geography-type tracts \
    --census-geography-years "2020 2010 2000" \
    --definition-vintage march_2020
```
