#!/usr/bin/env bash

if (( $# != 5 )); then
    printf 'Usage: %s YEAR GEOGRAPHY_TYPE STUDY_AREA_TYPE DEFINITION_VINTAGE OUTPUT_FILE\n' "$0" >&2
    exit 2
fi

year=$1
census_geography_type=$2
study_area_type=$3
definition_vintage=$4
output_file=$5

SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1
    pwd -P
)"
TOP_DIR="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"
cd "${TOP_DIR}"

output_dir="data/processed/clipped_geographies/${year}"
census_file="data/processed/census_geographies/${year}_${census_geography_type}.shp"
definition_pattern="data/processed/study_area_definitions/${study_area_type}_*_${definition_vintage}.shp"

mkdir -p "${output_dir}"
mkdir -p "$(dirname "${output_file}")"

echo "filename, target_name, source_area, overlap_area, overlap_percentage" > "${output_file}"

poetry run python pipeline/preprocessing/overlaps.py \
    "${census_file}" \
    "${definition_pattern}" \
    "${output_dir}" \
    --census-geography-type "${census_geography_type}" \
    --census-geography-year "${year}" \
    --definition-vintage "${definition_vintage}" \
    >> "${output_file}"
