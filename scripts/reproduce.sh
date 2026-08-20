#!/usr/bin/env bash
cd "$(dirname "${BASH_SOURCE[0]}")/.."

config="$(poetry run python pipeline/config.py)" || exit 1
eval "${config}"

# Set up folder structure.
bash scripts/setup.sh

# Save a log of the run configuration
RUN_STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
export METRIC_FAILURES_FILE="${RUN_OUTPUT_DIR}/metric_failures.csv"
{
    echo "start_timestamp=${RUN_STARTED_AT}"
    echo "graph_area_type=${STUDY_AREA_TYPE}"
    echo "nodes_area_type=${CENSUS_GEOGRAPHY_TYPE}"
    echo "study_area_source_file=${STUDY_AREA_SOURCE_FILE:-}"
    echo "census_geography_years=${CENSUS_GEOGRAPHY_YEARS}"
} > "${RUN_OUTPUT_DIR}/run.log"

# Download and join population values to census geography shapefiles.
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

# Generate study area definition shapefiles.
poetry run python pipeline/preprocessing/study_areas.py \
    ${STUDY_AREA_SOURCE_FILE:+--filename "${STUDY_AREA_SOURCE_FILE}"} \
    --study-area-type "${STUDY_AREA_TYPE}"

# Select census geographies that overlap with study area definition shapefiles.
poetry run python pipeline/preprocessing/overlaps.py \
    "data/processed/study_area_definitions/${STUDY_AREA_TYPE}_*_${STUDY_AREA_DEFINITION_VINTAGE}.gpkg" \
    "data/processed/clipped_geographies" \
    --census-geography-type "${CENSUS_GEOGRAPHY_TYPE}" \
    --census-geography-years "${CENSUS_GEOGRAPHY_YEARS}" \
    --definition-vintage "${STUDY_AREA_DEFINITION_VINTAGE}"

# Generate dual graphs.
poetry run python pipeline/graphs.py \
    "data/processed/clipped_geographies/*/${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}_*_${STUDY_AREA_DEFINITION_VINTAGE}_vintage.gpkg"

# Calculate metrics.
poetry run python pipeline/metrics.py \
    "data/processed/dual_graphs/*/${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}_*_${STUDY_AREA_DEFINITION_VINTAGE}_vintage_connected.json" \
    BLACK WHITE TOTPOP "${RUN_OUTPUT_DIR}/white_black.csv"

poetry run python pipeline/metrics.py \
    "data/processed/dual_graphs/*/${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}_*_${STUDY_AREA_DEFINITION_VINTAGE}_vintage_connected.json" \
    POC WHITE TOTPOP "${RUN_OUTPUT_DIR}/white_poc.csv"

# Generate figures
for metric in white_black white_poc; do
    poetry run python pipeline/visualization/generate_figures.py \
        --filename "${RUN_OUTPUT_DIR}/${metric}.csv" \
        --prefix "${metric}_${STUDY_AREA_TYPE}_${CENSUS_GEOGRAPHY_TYPE}" \
        --geography-type "${CENSUS_GEOGRAPHY_TYPE}" \
        --study-area-type "${STUDY_AREA_TYPE}"
done
