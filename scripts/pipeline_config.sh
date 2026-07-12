# Set these variables in the environment before running the pipeline to override the defaults below.
#
# Supported:
#   STUDY_AREA_TYPE: cbsa, county, counties
#   CENSUS_GEOGRAPHY_TYPE: tracts, block_groups, blocks, counties
#   STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE: counties

STUDY_AREA_TYPE="${STUDY_AREA_TYPE:-cbsa}"
CENSUS_GEOGRAPHY_TYPE="${CENSUS_GEOGRAPHY_TYPE:-tracts}"
CENSUS_GEOGRAPHY_YEARS="${CENSUS_GEOGRAPHY_YEARS:-2020 2010 2000 1990 1980}"
STUDY_AREA_VINTAGE="${STUDY_AREA_VINTAGE:-2020}"

case "${STUDY_AREA_TYPE}" in
    counties) STUDY_AREA_TYPE="county" ;;
    cbsa|county) ;;
    *)
        echo "Unsupported STUDY_AREA_TYPE=${STUDY_AREA_TYPE}. Use cbsa, county, or counties." >&2
        exit 1
        ;;
esac

case "${CENSUS_GEOGRAPHY_TYPE}" in
    tracts|block_groups|blocks|counties) ;;
    tract) CENSUS_GEOGRAPHY_TYPE="tracts" ;;
    block_group) CENSUS_GEOGRAPHY_TYPE="block_groups" ;;
    block) CENSUS_GEOGRAPHY_TYPE="blocks" ;;
    county) CENSUS_GEOGRAPHY_TYPE="counties" ;;
    *)
        echo "Unsupported CENSUS_GEOGRAPHY_TYPE=${CENSUS_GEOGRAPHY_TYPE}. Use tracts, block_groups, blocks, or counties." >&2
        exit 1
        ;;
esac

if [ "${CENSUS_GEOGRAPHY_TYPE}" = "block_groups" ]; then
    filtered_years=""
    for y in ${CENSUS_GEOGRAPHY_YEARS}; do
        if [ "${y}" = "1980" ]; then
            echo "Warning: Skipping 1980 for CENSUS_GEOGRAPHY_TYPE=block_groups — NHGIS does not publish 1980 block group boundary shapefiles." >&2
        else
            filtered_years="${filtered_years:+${filtered_years} }${y}"
        fi
    done
    CENSUS_GEOGRAPHY_YEARS="${filtered_years}"
fi

STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE="${STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE:-counties}"

case "${STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE}" in
    tracts|block_groups|blocks|counties) ;;
    tract) STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE="tracts" ;;
    block_group) STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE="block_groups" ;;
    block) STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE="blocks" ;;
    county) STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE="counties" ;;
    *)
        echo "Unsupported STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE=${STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE}. Use tracts, block_groups, blocks, or counties. For STUDY_AREA_TYPE=cbsa, use counties." >&2
        exit 1
        ;;
esac

STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR="${STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR:-${STUDY_AREA_VINTAGE}}"

if [ "${STUDY_AREA_TYPE}" = "cbsa" ]; then
    STUDY_AREA_SOURCE_PATTERN="${STUDY_AREA_SOURCE_PATTERN:-list1_*_${STUDY_AREA_VINTAGE}.xls}"

    if [ -z "${STUDY_AREA_SOURCE_FILE:-}" ]; then
        STUDY_AREA_SOURCE_FILE="$(find study_area_sources -maxdepth 1 -name "${STUDY_AREA_SOURCE_PATTERN}" | sort | tail -n 1)"
    fi

    if [ -z "${STUDY_AREA_SOURCE_FILE:-}" ]; then
        echo "No study area source file found for STUDY_AREA_TYPE=${STUDY_AREA_TYPE}, STUDY_AREA_VINTAGE=${STUDY_AREA_VINTAGE}, STUDY_AREA_SOURCE_PATTERN=${STUDY_AREA_SOURCE_PATTERN}" >&2
        exit 1
    fi

    if [ -z "${STUDY_AREA_DEFINITION_VINTAGE:-}" ]; then
        STUDY_AREA_SOURCE_STEM="$(basename "${STUDY_AREA_SOURCE_FILE}")"
        STUDY_AREA_SOURCE_STEM="${STUDY_AREA_SOURCE_STEM%.*}"
        STUDY_AREA_DEFINITION_VINTAGE="${STUDY_AREA_SOURCE_STEM#list1_}"
    fi
else
    STUDY_AREA_SOURCE_FILE="${STUDY_AREA_SOURCE_FILE:-}"
    STUDY_AREA_SOURCE_PATTERN="${STUDY_AREA_SOURCE_PATTERN:-}"
    STUDY_AREA_DEFINITION_VINTAGE="${STUDY_AREA_DEFINITION_VINTAGE:-${STUDY_AREA_VINTAGE}}"
fi

STUDY_AREA_DEFINITION_GEOGRAPHIES="${STUDY_AREA_DEFINITION_GEOGRAPHIES:-census_geographies/${STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR}_${STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE}.shp}"


OUTPUT_SUFFIX="${STUDY_AREA_TYPE}_${CENSUS_GEOGRAPHY_TYPE}_${STUDY_AREA_DEFINITION_VINTAGE}"
RUN_NAME="${RUN_NAME:-${CENSUS_GEOGRAPHY_TYPE}_in_${STUDY_AREA_TYPE}}"
RUN_OUTPUT_DIR="${RUN_OUTPUT_DIR:-outputs/${RUN_NAME}}"
