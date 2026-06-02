## CAPY

## Testing
```
pytest
```

## Reproducing
First, install the [dependencies](#dependencies).

Next, download the [nhgis](https://nhgis.org) race and shapefile data for Census tracts (from 1970-2020 inclusive) into the `nhgis` folder.

To get population data, look for `B18. Persons by Race [5*]` in the Time Series tab. Add it to the data cart and click continue. In the cart, add years 1970, 1980, 1990, 2000, 2010, 2020 and Census Tracts as geography. To get GIS files, go back to the data selection window and in the GIS files tab pick all Census Tracts for the same years.

The code expects this structure in `nhgis`.

```
nhgis/
└── **/ # intermediary folder(s) as downloaded from NHGIS.
    ├── ... one CSV for each year, e.g. nhgis0001_ts_nominal_tract_1970.csv ...
    └── ... one shapefile for each year, with tract_YEAR in titles ...
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
