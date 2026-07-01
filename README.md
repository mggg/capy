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

Finally, run the reproduce script to rerun the analysis pipeline:
```
bash reproduce.sh
```

Your outputs will be in the `outputs/` folder.

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
