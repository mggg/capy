# capy_core/download

Scripts that fetch raw source data from external APIs and write it to `data/shared/raw/`.

## Scripts

### `download_geographies.py`

Downloads Census geography boundary files for each requested level and year.

- **2000–2020**: fetches TIGER/Line shapefiles directly from the Census FTP (no API key required). One `.zip` per state is downloaded and extracted into `data/shared/raw/geographies/census_{year}_{level}/`.
- **1980–1990**: submits an IPUMS/NHGIS extract request for the appropriate shapefile package and polls until it is ready, then downloads and saves it to `data/shared/raw/geographies/ipums_geography_extracts/{year}/{level}/`. Requires `IPUMS_API_KEY`.

```bash
poetry run python capy_core/download/download_geographies.py \
    --level tracts \
    --years "2020 2010 2000"
```

### `download_population_tables.py`

Downloads decennial census race and ethnicity counts (TOTPOP, NH_WHITE, NH_BLACK, etc.) for each requested level and year.

- **2000–2020**: queries the Census Decennial API state-by-state and writes one CSV per level/year to `data/shared/raw/population/census_{year}_{level}.csv`. Requires `CENSUS_API_KEY`.
- **1980–1990**: submits an IPUMS/NHGIS extract and polls until ready, then saves the result to `data/shared/raw/population/nhgis_{year}_{level}.csv`. Requires `IPUMS_API_KEY`.

```bash
poetry run python capy_core/download/download_population_tables.py \
    --level tracts \
    --years "2020 2010 2000"
```

## Required environment variables

| Variable | Used by |
|---|---|
| `CENSUS_API_KEY` | `download_population_tables.py` (2000–2020 population) |
| `IPUMS_API_KEY` | both scripts (1980–1990 data) |
