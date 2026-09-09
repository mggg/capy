#!/usr/bin/env bash

SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1
    pwd -P
)"
TOP_DIR="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"
cd "${TOP_DIR}"

_config="$(poetry run python capy_core/config.py)" || exit 1
eval "${_config}"
IFS=" " read -r -a census_geography_years <<< "${CENSUS_GEOGRAPHY_YEARS}"

mkdir -p data/shared/raw/study_area_sources
mkdir -p data/shared/raw/geographies
mkdir -p data/shared/raw/geographies/ipums_geography_extracts
mkdir -p data/shared/raw/geographies/ipums_geography_extracts/1980
mkdir -p data/shared/raw/geographies/ipums_geography_extracts/1990
mkdir -p data/shared/raw/population
mkdir -p data/shared/raw/population/ipums_population_extracts
mkdir -p data/shared/processed/census_geographies
mkdir -p data/shared/processed/study_area_definitions

for year in "${census_geography_years[@]}"; do
    mkdir -p "data/shared/processed/clipped_geographies/${year}"
    mkdir -p "data/shared/processed/dual_graphs/${year}"
done

mkdir -p "${RUN_OUTPUT_DIR}"
mkdir -p data/shared/outputs
