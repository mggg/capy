#!/usr/bin/env bash

set -euo pipefail

. scripts/pipeline_config.sh

if [ "${STUDY_AREA_TYPE}" = "cbsa" ] || [ "${STUDY_AREA_TYPE}" = "max_county" ] || [ "${STUDY_AREA_TYPE}" = "max_city" ]; then
    python pipeline/build_study_areas.py \
        --filename "${STUDY_AREA_SOURCE_FILE}" \
        --definition-geographies "${STUDY_AREA_DEFINITION_GEOGRAPHIES}" \
        --output-dir "study_areas/definitions" \
        --study-area-type "${STUDY_AREA_TYPE}" \
        --definition-vintage "${STUDY_AREA_DEFINITION_VINTAGE}" \
        --cbsa-geographies "census_geographies/${STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR}_counties.shp" 

else
    python pipeline/build_study_areas.py \
        --definition-geographies "${STUDY_AREA_DEFINITION_GEOGRAPHIES}" \
        --output-dir "study_areas/definitions" \
        --study-area-type "${STUDY_AREA_TYPE}" \
        --definition-vintage "${STUDY_AREA_DEFINITION_VINTAGE}"
fi
