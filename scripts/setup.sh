#!/usr/bin/env bash

set -euo pipefail

. scripts/pipeline_config.sh

mkdir -p data/interim/study_area_sources
mkdir -p data/raw/geographies
mkdir -p data/raw/geographies/ipums_geography_extracts
mkdir -p data/raw/geographies/ipums_geography_extracts/1980
mkdir -p data/raw/geographies/ipums_geography_extracts/1990
mkdir -p data/raw/population
mkdir -p data/raw/population/ipums_population_extracts
mkdir -p data/interim/census_geographies
mkdir -p data/interim/study_areas/definitions

for year in ${CENSUS_GEOGRAPHY_YEARS}; do
    mkdir -p "data/interim/study_areas/${year}"
done

mkdir -p "${RUN_OUTPUT_DIR}"
mkdir -p data/outputs
