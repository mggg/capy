#!/usr/bin/env bash

set -euo pipefail

. scripts/pipeline_config.sh

if [ "${STUDY_AREA_TYPE}" = "cbsa" ]; then
    python pipeline/build_study_areas.py \
        --filename "${STUDY_AREA_SOURCE_FILE}" \
        --definition-geographies "${STUDY_AREA_DEFINITION_GEOGRAPHIES}" \
        --output-dir "study_areas/definitions" \
        --study-area-type "${STUDY_AREA_TYPE}" \
        --definition-vintage "${STUDY_AREA_DEFINITION_VINTAGE}"
else
    python pipeline/build_study_areas.py \
        --definition-geographies "${STUDY_AREA_DEFINITION_GEOGRAPHIES}" \
        --output-dir "study_areas/definitions" \
        --study-area-type "${STUDY_AREA_TYPE}" \
        --definition-vintage "${STUDY_AREA_DEFINITION_VINTAGE}"
fi
