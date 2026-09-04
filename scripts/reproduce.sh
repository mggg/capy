#!/usr/bin/env bash
cd "$(dirname "${BASH_SOURCE[0]}")/.."

config="$(poetry run python pipeline/config.py)" || exit 1
eval "${config}"

# Set up folder structure
bash scripts/setup.sh

# Save a log of the run configuration
RUN_STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
export PIPELINE_LOG_FILE="${RUN_OUTPUT_DIR}/run.log"
export METRIC_FAILURES_FILE="${RUN_OUTPUT_DIR}/metric_failures.csv"
{
    echo "start_timestamp=${RUN_STARTED_AT}"
    echo "graph_area_type=${STUDY_AREA_TYPE}"
    echo "nodes_area_type=${CENSUS_GEOGRAPHY_TYPE}"
    echo "study_area_source_file=${STUDY_AREA_SOURCE_FILE:-}"
    echo "census_geography_years=${CENSUS_GEOGRAPHY_YEARS}"
    echo ""
} > "${PIPELINE_LOG_FILE}"

# Write to the log file
exec > >(tee -a "${PIPELINE_LOG_FILE}") 2>&1

echo "=== 1. Download ==="
poetry run python pipeline/download/download_population_tables.py --level "${CENSUS_GEOGRAPHY_TYPE}"
poetry run python pipeline/download/download_geographies.py --level "${CENSUS_GEOGRAPHY_TYPE}"
poetry run python pipeline/preprocessing/census_geographies.py --level "${CENSUS_GEOGRAPHY_TYPE}"

# Only download study-area-definition geographies separately when they differ from the census geography type/year already fetched above (avoids a redundant download).
if [ "${STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE}" != "${CENSUS_GEOGRAPHY_TYPE}" ] ||
    [[ " ${CENSUS_GEOGRAPHY_YEARS} " != *" ${STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR} "* ]]; then
    poetry run python pipeline/download/download_population_tables.py \
        --level "${STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE}" --years "${STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR}"
    poetry run python pipeline/download/download_geographies.py \
        --level "${STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE}" --years "${STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR}"
    poetry run python pipeline/preprocessing/census_geographies.py \
        --level "${STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE}" --years "${STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR}"
fi

echo ""
echo "=== 2. Study areas ==="
poetry run python pipeline/preprocessing/study_areas.py \
    ${STUDY_AREA_SOURCE_FILE:+--filename "${STUDY_AREA_SOURCE_FILE}"} \
    --study-area-type "${STUDY_AREA_TYPE}"
echo "Study areas are saved to `data/processed/study_area_definitions`."

echo ""
echo "=== 3. Overlaps ==="
poetry run python pipeline/preprocessing/overlaps.py \
    "data/processed/study_area_definitions/${STUDY_AREA_TYPE}_*_${STUDY_AREA_DEFINITION_VINTAGE}.gpkg" \
    "data/processed/clipped_geographies" \
    --census-geography-type "${CENSUS_GEOGRAPHY_TYPE}" \
    --census-geography-years "${CENSUS_GEOGRAPHY_YEARS}" \
    --definition-vintage "${STUDY_AREA_DEFINITION_VINTAGE}"

echo ""
echo "=== 4. Graphs ==="
poetry run python pipeline/graphs.py \
    "data/processed/clipped_geographies/*/${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}_*_${STUDY_AREA_DEFINITION_VINTAGE}_vintage.gpkg"

echo ""
echo "=== 5. Metrics ==="
poetry run python pipeline/metrics.py \
    "data/processed/dual_graphs/*/${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}_*_${STUDY_AREA_DEFINITION_VINTAGE}_vintage_connected.json" \
    BLACK WHITE TOTPOP "${RUN_OUTPUT_DIR}/white_black.csv"

poetry run python pipeline/metrics.py \
    "data/processed/dual_graphs/*/${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}_*_${STUDY_AREA_DEFINITION_VINTAGE}_vintage_connected.json" \
    POC WHITE TOTPOP "${RUN_OUTPUT_DIR}/white_poc.csv"

echo ""
echo "=== 6. Figures ==="
for metric in white_black white_poc; do
    poetry run python pipeline/visualization/generate_figures.py \
        --filename "${RUN_OUTPUT_DIR}/${metric}.csv" \
        --prefix "${metric}_${STUDY_AREA_TYPE}_${CENSUS_GEOGRAPHY_TYPE}" \
        --geography-type "${CENSUS_GEOGRAPHY_TYPE}" \
        --study-area-type "${STUDY_AREA_TYPE}"
done
echo "Saved to ${RUN_OUTPUT_DIR}/figures"
