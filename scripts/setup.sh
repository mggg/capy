#!/usr/bin/env bash

set -euo pipefail

. scripts/pipeline_config.sh

mkdir -p study_area_sources
mkdir -p census_raw/geographies
mkdir -p census_raw/geographies/ipums_geography_extracts
mkdir -p census_raw/geographies/ipums_geography_extracts/1980
mkdir -p census_raw/geographies/ipums_geography_extracts/1990
mkdir -p census_raw/population
mkdir -p census_raw/population/ipums_population_extracts
mkdir -p census_geographies
mkdir -p study_areas/definitions

for year in ${CENSUS_GEOGRAPHY_YEARS}; do
    mkdir -p "study_areas/${year}"
done

mkdir -p "${RUN_OUTPUT_DIR}"
mkdir -p outputs
