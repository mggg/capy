#!/usr/bin/env bash


SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1
    pwd -P
)"
TOP_DIR="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"
cd "${TOP_DIR}"

_config="$(poetry run python scripts/resolve_config.py)" || exit 1
eval "${_config}"
IFS=" " read -r -a census_geography_years <<< "${CENSUS_GEOGRAPHY_YEARS}"

mkdir -p data/raw/study_area_sources
mkdir -p data/raw/geographies
mkdir -p data/raw/geographies/ipums_geography_extracts
mkdir -p data/raw/geographies/ipums_geography_extracts/1980
mkdir -p data/raw/geographies/ipums_geography_extracts/1990
mkdir -p data/raw/population
mkdir -p data/raw/population/ipums_population_extracts
mkdir -p data/processed/census_geographies
mkdir -p data/processed/study_area_definitions

for year in "${census_geography_years[@]}"; do
    mkdir -p "data/processed/clipped_geographies/${year}"
    mkdir -p "data/processed/dual_graphs/${year}"
done

mkdir -p "${RUN_OUTPUT_DIR}"
mkdir -p outputs
