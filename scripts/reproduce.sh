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

build_geography_inputs() {
    local geography_type="$1"
    local geography_years="$2"

    poetry run python pipeline/download/download_population_tables.py \
        --level "${geography_type}" \
        --years "${geography_years}"
    poetry run python pipeline/download/download_geographies.py \
        --level "${geography_type}" \
        --years "${geography_years}"
    poetry run python pipeline/preprocessing/census_geographies.py \
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
    poetry run python pipeline/metrics.py "" "$@" --headers-only > "${output_file}"
    for year in "${census_geography_years[@]}"; do
        find "data/processed/dual_graphs/${year}" -type f \
            -name "${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}_*_${year}_${STUDY_AREA_DEFINITION_VINTAGE}_vintage_connected.json" |
            parallel --bar poetry run python pipeline/metrics.py {} "$@" >> "${output_file}"
    done
}

# Set up folder structure.
bash "${SCRIPT_DIR}/setup.sh"

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
    ! year_list_contains "${STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR}" "${census_geography_years[@]}"; then
    build_geography_inputs \
        "${STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE}" \
        "${STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR}"
fi

# Generate study area definition shapefiles.
bash "${SCRIPT_DIR}/build_study_areas.sh"

# Select census geographies that overlap with study area definition shapefiles.
bash "${SCRIPT_DIR}/overlaps.sh"

# Generate dual graphs.
_build_graph() {
    local shp="$1"
    local stem
    stem="$(basename "${shp%.gpkg}")"
    local dual_dir
    dual_dir="data/processed/dual_graphs/$(basename "$(dirname "$shp")")"
    poetry run python pipeline/graphs.py "$shp" "${dual_dir}/${stem}_orig.json" "${dual_dir}/${stem}_connected.json"
}
export -f _build_graph

for year in "${census_geography_years[@]}"; do
    find "data/processed/clipped_geographies/${year}" \
        -type f \
        -name "${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}_*_${year}_${STUDY_AREA_DEFINITION_VINTAGE}_vintage.gpkg"
done |
    parallel --bar _build_graph {}

# Calculate metrics.
calculate_csv "${RUN_OUTPUT_DIR}/white_black.csv" BLACK WHITE TOTPOP
calculate_csv "${RUN_OUTPUT_DIR}/white_poc.csv"   POC   WHITE TOTPOP

# Generate figures under the configured run output. The figure script enriches
# raw metric CSVs with study-area metadata as needed.
for metric in white_black white_poc; do
    poetry run python pipeline/visualization/generate_figures.py \
        --filename "${RUN_OUTPUT_DIR}/${metric}.csv" \
        --prefix "${metric}_${STUDY_AREA_TYPE}_${CENSUS_GEOGRAPHY_TYPE}" \
        --geography-type "${CENSUS_GEOGRAPHY_TYPE}"
done
