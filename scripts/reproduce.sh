#!/usr/bin/env bash

set -euxo pipefail

. scripts/pipeline_config.sh

build_geography_inputs() {
    local geography_type="$1"
    local geography_years="$2"

    python pipeline/download_population_tables.py \
        --level "${geography_type}" \
        --years "${geography_years}"
    python pipeline/download_geographies.py \
        --level "${geography_type}" \
        --years "${geography_years}"
    python pipeline/build_census_geographies.py \
        --level "${geography_type}" \
        --years "${geography_years}"
}

year_list_contains() {
    local needle="$1"
    shift
    local year
    for year in "$@"; do
        if [ "${year}" = "${needle}" ]; then
            return 0
        fi
    done
    return 1
}

# Set up folder structure.
bash scripts/setup.sh

RUN_STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
export METRIC_FAILURES_FILE="${RUN_OUTPUT_DIR}/metric_failures.csv"
{
    echo "start_timestamp=${RUN_STARTED_AT}"
    echo "run_name=${RUN_NAME}"
    echo "run_output_dir=${RUN_OUTPUT_DIR}"
    echo ""
    echo "graph_area_type=${STUDY_AREA_TYPE}"
    echo "nodes_area_type=${CENSUS_GEOGRAPHY_TYPE}"
    echo ""
    echo "study_area_vintage=${STUDY_AREA_VINTAGE}"
    echo "study_area_definition_vintage=${STUDY_AREA_DEFINITION_VINTAGE}"
    echo "study_area_source_file=${STUDY_AREA_SOURCE_FILE:-}"
    echo "study_area_definition_geography_type=${STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE}"
    echo "study_area_definition_geography_year=${STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR}"
    echo "study_area_definition_geographies=${STUDY_AREA_DEFINITION_GEOGRAPHIES}"
    echo "study_area_definition_glob=study_areas/definitions/${STUDY_AREA_TYPE}_*_${STUDY_AREA_DEFINITION_VINTAGE}.shp"
    echo ""
    echo "census_geography_years=${CENSUS_GEOGRAPHY_YEARS}"
    echo "reference_census_geography_year=${REFERENCE_CENSUS_GEOGRAPHY_YEAR}"
    echo "reference_overlap=${REFERENCE_OVERLAP}"
} > "${RUN_OUTPUT_DIR}/run.log"

# Download and join population values to census geography shapefiles.
build_geography_inputs "${CENSUS_GEOGRAPHY_TYPE}" "${CENSUS_GEOGRAPHY_YEARS}"
if [ "${STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE}" != "${CENSUS_GEOGRAPHY_TYPE}" ] ||
    ! year_list_contains "${STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR}" ${CENSUS_GEOGRAPHY_YEARS}; then
    build_geography_inputs \
        "${STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE}" \
        "${STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR}"
fi

# Generate study area definition shapefiles.
bash scripts/build_study_areas.sh

# Select census geographies that overlap with study area definition shapefiles.
bash scripts/overlaps.sh

# Generate dual graphs.
for year in ${CENSUS_GEOGRAPHY_YEARS}; do
    find "study_areas/${year}" \
        -type f \
        -name "${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}_*_${year}_${STUDY_AREA_DEFINITION_VINTAGE}_vintage.shp"
done |
    parallel --bar python pipeline/gen_duals.py {} {.}_orig.json {.}_connected.json

# Calculate metrics, but first generate headers.
python pipeline/calculate_metrics.py "study_areas/${REFERENCE_CENSUS_GEOGRAPHY_YEAR}/${REFERENCE_OVERLAP}_connected.json" BLACK WHITE TOTPOP --headers-only > "${RUN_OUTPUT_DIR}/white_black.csv"
for year in ${CENSUS_GEOGRAPHY_YEARS}; do
    find "study_areas/${year}" \
        -type f \
        -name "${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}_*_${year}_${STUDY_AREA_DEFINITION_VINTAGE}_vintage_connected.json" |
        parallel --bar python pipeline/calculate_metrics.py {} BLACK WHITE TOTPOP >> "${RUN_OUTPUT_DIR}/white_black.csv"
done

python pipeline/calculate_metrics.py "study_areas/${REFERENCE_CENSUS_GEOGRAPHY_YEAR}/${REFERENCE_OVERLAP}_connected.json" POC WHITE TOTPOP --headers-only > "${RUN_OUTPUT_DIR}/white_poc.csv"
for year in ${CENSUS_GEOGRAPHY_YEARS}; do
    find "study_areas/${year}" \
        -type f \
        -name "${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}_*_${year}_${STUDY_AREA_DEFINITION_VINTAGE}_vintage_connected.json" |
        parallel --bar python pipeline/calculate_metrics.py {} POC WHITE TOTPOP >> "${RUN_OUTPUT_DIR}/white_poc.csv"
done

# Generate figures under the configured run output. The figure script enriches
# raw metric CSVs with study-area metadata as needed.
python pipeline/generate_figures.py \
    --filename "${RUN_OUTPUT_DIR}/white_poc.csv" \
    --prefix "white_poc_${OUTPUT_SUFFIX}"
python pipeline/generate_figures.py \
    --filename "${RUN_OUTPUT_DIR}/white_black.csv" \
    --prefix "white_black_${OUTPUT_SUFFIX}"
