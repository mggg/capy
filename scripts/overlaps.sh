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

parallel --bar \
    bash "${SCRIPT_DIR}/run_overlap.sh" \
    {} \
    "${CENSUS_GEOGRAPHY_TYPE}" \
    "${STUDY_AREA_TYPE}" \
    "${STUDY_AREA_DEFINITION_VINTAGE}" \
    ::: "${census_geography_years[@]}"
