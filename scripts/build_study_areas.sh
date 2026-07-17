#!/usr/bin/env bash


SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1
    pwd -P
)"
TOP_DIR="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"
cd "${TOP_DIR}"

_config="$(poetry run python scripts/resolve_config.py)" || exit 1
eval "${_config}"

if [ "${STUDY_AREA_TYPE}" = "cbsa" ]; then
    poetry run python pipeline/preprocessing/study_areas.py \
        --filename "${STUDY_AREA_SOURCE_FILE}" \
        --definition-geographies "${STUDY_AREA_DEFINITION_GEOGRAPHIES}" \
        --output-dir "data/processed/study_area_definitions" \
        --study-area-type "${STUDY_AREA_TYPE}" \
        --definition-vintage "${STUDY_AREA_DEFINITION_VINTAGE}"
else
    poetry run python pipeline/preprocessing/study_areas.py \
        --definition-geographies "${STUDY_AREA_DEFINITION_GEOGRAPHIES}" \
        --output-dir "data/processed/study_area_definitions" \
        --study-area-type "${STUDY_AREA_TYPE}" \
        --definition-vintage "${STUDY_AREA_DEFINITION_VINTAGE}"
fi
