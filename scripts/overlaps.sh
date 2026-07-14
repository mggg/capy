#!/usr/bin/env bash

set -euo pipefail

. scripts/pipeline_config.sh

COVERAGE_STATS_FILE="${RUN_OUTPUT_DIR}/coverage_stats.csv"

mkdir -p "${RUN_OUTPUT_DIR}"

echo "filename, target_name, source_area, overlap_area, overlap_percentage" > "${COVERAGE_STATS_FILE}"

parallel --bar --keep-order \
    "mkdir -p \"data/interim/study_areas/{}\" && python pipeline/build/overlaps.py \
        \"data/interim/census_geographies/{}_${CENSUS_GEOGRAPHY_TYPE}.shp\" \
        \"data/interim/study_areas/definitions/${STUDY_AREA_TYPE}_*_${STUDY_AREA_DEFINITION_VINTAGE}.shp\" \
        \"data/interim/study_areas/{}\" \
        --census-geography-type \"${CENSUS_GEOGRAPHY_TYPE}\" \
        --census-geography-year \"{}\" \
        --definition-vintage \"${STUDY_AREA_DEFINITION_VINTAGE}\"" \
    ::: ${CENSUS_GEOGRAPHY_YEARS} \
    >> "${COVERAGE_STATS_FILE}"
