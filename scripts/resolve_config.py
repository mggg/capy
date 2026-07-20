#!/usr/bin/env python3
"""
Read pipeline/config.yaml, apply normalization/validation/file-finding logic,
and print shell export statements to stdout.  Intended to be consumed via:

    eval "$(poetry run python scripts/resolve_config.py)"

Must be run from the repository root (all caller scripts guarantee this
via cd "${TOP_DIR}" before invoking).
"""
import glob
import os
import shlex
import sys

import yaml


def _normalize(value: str, aliases: dict[str, str], valid: set[str], name: str) -> str:
    value = aliases.get(value, value)
    if value not in valid:
        print(f"Unsupported {name}={value!r}. Valid values: {', '.join(sorted(valid))}.", file=sys.stderr)
        sys.exit(1)
    return value


def main() -> None:
    with open("pipeline/config.yaml") as f:
        cfg = yaml.safe_load(f)

    study_area_type = os.environ.get("STUDY_AREA_TYPE", str(cfg["study_area_type"]))
    study_area_type = _normalize(
        study_area_type,
        {"counties": "county"},
        {"cbsa", "county"},
        "STUDY_AREA_TYPE",
    )

    census_geography_type = os.environ.get("CENSUS_GEOGRAPHY_TYPE", str(cfg["census_geography_type"]))
    census_geography_type = _normalize(
        census_geography_type,
        {"tract": "tracts", "block_group": "block_groups", "block": "blocks", "county": "counties"},
        {"tracts", "block_groups", "blocks", "counties"},
        "CENSUS_GEOGRAPHY_TYPE",
    )

    years_raw = os.environ.get("CENSUS_GEOGRAPHY_YEARS", "")
    years = years_raw.split() if years_raw else [str(y) for y in cfg["census_geography_years"]]
    if census_geography_type in ("block_groups", "blocks") and "1980" in years:
        print(
            f"Warning: Skipping 1980 for CENSUS_GEOGRAPHY_TYPE={census_geography_type} — "
            "NHGIS does not publish 1980 block group or block boundary shapefiles.",
            file=sys.stderr,
        )
        years = [y for y in years if y != "1980"]
    census_geography_years = " ".join(years)

    study_area_vintage = os.environ.get("STUDY_AREA_VINTAGE", str(cfg.get("study_area_vintage", "2020")))

    study_area_definition_geography_type = os.environ.get(
        "STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE",
        str(cfg.get("study_area_definition_geography_type", "counties")),
    )
    study_area_definition_geography_type = _normalize(
        study_area_definition_geography_type,
        {"tract": "tracts", "block_group": "block_groups", "block": "blocks", "county": "counties"},
        {"tracts", "block_groups", "blocks", "counties"},
        "STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE",
    )

    study_area_definition_geography_year = os.environ.get(
        "STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR", study_area_vintage
    )

    study_area_source_pattern = os.environ.get(
        "STUDY_AREA_SOURCE_PATTERN", f"list1_*_{study_area_vintage}.xls"
    )
    study_area_source_file = os.environ.get("STUDY_AREA_SOURCE_FILE", "")
    study_area_definition_vintage = os.environ.get("STUDY_AREA_DEFINITION_VINTAGE", "")

    if study_area_type == "cbsa":
        if not study_area_source_file:
            matches = sorted(glob.glob(f"data/raw/study_area_sources/{study_area_source_pattern}"))
            if not matches:
                print(
                    f"No study area source file found for STUDY_AREA_TYPE={study_area_type}, "
                    f"STUDY_AREA_VINTAGE={study_area_vintage}, "
                    f"STUDY_AREA_SOURCE_PATTERN={study_area_source_pattern}",
                    file=sys.stderr,
                )
                sys.exit(1)
            study_area_source_file = matches[-1]

        if not study_area_definition_vintage:
            stem = os.path.splitext(os.path.basename(study_area_source_file))[0]
            study_area_definition_vintage = stem.removeprefix("list1_")
    else:
        study_area_definition_vintage = study_area_definition_vintage or study_area_vintage

    study_area_definition_geographies = os.environ.get(
        "STUDY_AREA_DEFINITION_GEOGRAPHIES",
        f"data/processed/census_geographies/{study_area_definition_geography_year}_{study_area_definition_geography_type}.gpkg",
    )

    run_name = os.environ.get("RUN_NAME", f"{census_geography_type}_in_{study_area_type}")
    run_output_dir = os.environ.get("RUN_OUTPUT_DIR", f"outputs/{run_name}")

    exports = {
        "STUDY_AREA_TYPE": study_area_type,
        "CENSUS_GEOGRAPHY_TYPE": census_geography_type,
        "CENSUS_GEOGRAPHY_YEARS": census_geography_years,
        "STUDY_AREA_VINTAGE": study_area_vintage,
        "STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE": study_area_definition_geography_type,
        "STUDY_AREA_DEFINITION_GEOGRAPHY_YEAR": study_area_definition_geography_year,
        "STUDY_AREA_SOURCE_PATTERN": study_area_source_pattern,
        "STUDY_AREA_SOURCE_FILE": study_area_source_file,
        "STUDY_AREA_DEFINITION_VINTAGE": study_area_definition_vintage,
        "STUDY_AREA_DEFINITION_GEOGRAPHIES": study_area_definition_geographies,
        "OUTPUT_SUFFIX": f"{study_area_type}_{census_geography_type}_{study_area_definition_vintage}",
        "RUN_NAME": run_name,
        "RUN_OUTPUT_DIR": run_output_dir,
    }

    for key, value in exports.items():
        print(f"export {key}={shlex.quote(value)}")


if __name__ == "__main__":
    main()
