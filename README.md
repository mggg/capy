## CAPY

## Testing
```
pytest
```

## Reproducing
First, install the [dependencies](#dependencies).
Then, setup the folder structure:
```
bash scripts/setup.sh  # setup folder structure
```

Next, download the [nhgis](https://nhgis.org) race and shapefile data for Census tracts (from 1970-2020 inclusive) into the `nhgis` folder.

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
