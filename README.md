## CAPY

## Testing
```
pytest
```

## Reproducing
First, install the [dependencies](#dependencies).

Raw Census inputs are downloaded into `census_raw/`. Population and geography data come from two sources:

- 1980 and 1990: NHGIS via the IPUMS API.
- 2000, 2010, and 2020: Census API/TIGER downloads.

Set API keys in your shell before downloading data:
```
export CENSUS_API_KEY="..."
export IPUMS_API_KEY="..."
```

The pipeline is configured through environment variables consumed by `scripts/pipeline_config.sh`.
The default run uses CBSA study areas and tract nodes for 2020, 2010, 2000, 1990, and 1980.
CBSA source spreadsheets live in `study_area_sources/`.

Finally, run the reproduce script to rerun the analysis pipeline:
```
bash scripts/reproduce.sh
```

Your outputs will be in a run-specific folder under `outputs/`, with figures in that folder's `figures/` subdirectory.

### Dependencies
Python deps are managed via Poetry. Install Python `3.9.10`, then install the Python deps by running:
```
pip install poetry
poetry install
```

To launch a shell with the poetry enviroment activated, run:
```
poetry shell
```

[`fd`](https://github.com/sharkdp/fd) is also required to run the reproduce script.
