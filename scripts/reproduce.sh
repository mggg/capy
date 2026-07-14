#!/usr/bin/env bash

set -euxo pipefail

. scripts/pipeline_config.sh

build_geography_inputs() {
    local geography_type="$1"
    local geography_years="$2"

    python pipeline/download/download_population_tables.py \
        --level "${geography_type}" \
        --years "${geography_years}"
    python pipeline/download/download_geographies.py \
        --level "${geography_type}" \
        --years "${geography_years}"
    python pipeline/build/build_census_geographies.py \
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

calculate_csv() {
    local output_file="$1"; shift
    python pipeline/metrics/calculate_metrics.py "" "$@" --headers-only > "${output_file}"
    for year in ${CENSUS_GEOGRAPHY_YEARS}; do
        find "data/interim/study_areas/${year}" -type f \
            -name "${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}_*_${year}_${STUDY_AREA_DEFINITION_VINTAGE}_vintage_connected.json" |
            parallel --bar python pipeline/metrics/calculate_metrics.py {} "$@" >> "${output_file}"
    done
}

# Set up folder structure.
bash scripts/setup.sh

# Save a log of the run configuration
RUN_STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
export METRIC_FAILURES_FILE="${RUN_OUTPUT_DIR}/metric_failures.csv"
{
    echo "run_name=${RUN_NAME}"
    echo "start_timestamp=${RUN_STARTED_AT}"
    echo ""
    echo "graph_area_type=${STUDY_AREA_TYPE}"
    echo "nodes_area_type=${CENSUS_GEOGRAPHY_TYPE}"
    echo ""
    echo "study_area_source_file=${STUDY_AREA_SOURCE_FILE:-}"
    echo ""
    echo "census_geography_years=${CENSUS_GEOGRAPHY_YEARS}"

} > "${RUN_OUTPUT_DIR}/run.log"

# Download and join population values to census geography shapefiles.
build_geography_inputs "${CENSUS_GEOGRAPHY_TYPE}" "${CENSUS_GEOGRAPHY_YEARS}"
# Only download study-area-definition geographies separately when they differ from
# the census geography type/year already fetched above (avoids a redundant download).
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
    find "data/interim/study_areas/${year}" \
        -type f \
        -name "${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}_*_${year}_${STUDY_AREA_DEFINITION_VINTAGE}_vintage.shp"
done |
    parallel --bar python pipeline/build/gen_duals.py {} {.}_orig.json {.}_connected.json

# Calculate metrics.
calculate_csv "${RUN_OUTPUT_DIR}/white_black.csv" BLACK WHITE TOTPOP
calculate_csv "${RUN_OUTPUT_DIR}/white_poc.csv"   POC   WHITE TOTPOP

# Generate figures under the configured run output. The figure script enriches
# raw metric CSVs with study-area metadata as needed.
for metric in white_black white_poc; do
    python pipeline/viz/generate_figures.py \
        --filename "${RUN_OUTPUT_DIR}/${metric}.csv" \
        --prefix "${metric}_${STUDY_AREA_TYPE}_${CENSUS_GEOGRAPHY_TYPE}" \
        --geography-type "${CENSUS_GEOGRAPHY_TYPE}"
done
