# data/shared/processed

Intermediate files produced by the preprocessing steps of the pipeline. Each subfolder is written by a specific script and consumed by the next step.

| Subfolder | Produced by | Contents |
|---|---|---|
| `census_geographies/{level}/` | `preprocessing/census_geographies.py` | Population-attributed `.gpkg` files, one per state-year. |
| `study_area_definitions/` | `preprocessing/study_areas.py` | One `.gpkg` (boundary polygon) + `.json` (metadata) per study area. |
| `clipped_geographies/{year}/` | `preprocessing/overlaps.py` | Census units clipped to each study area boundary, one `.gpkg` per study area-year. |
| `dual_graphs/{year}/` | `graphs.py` | Adjacency graph JSONs (`*_orig.json` and `*_connected.json`) per study area-year. |
