"""
Pipeline configuration loader. Reads pipeline/config.yaml and returns a plain dict of resolved config values.

Usage from Python:
    from pipeline.config import load_config
    cfg = load_config()

When run directly, prints shell export statements for use in shell scripts:
    eval "$(poetry run python pipeline/config.py)"
"""
from __future__ import annotations
import glob
import sys
from pathlib import Path
import yaml

CONFIG_FILE = Path(__file__).with_name("config.yaml")
REPO_ROOT = Path(__file__).parent.parent

STUDY_AREA_TYPE_ALIASES = {"counties": "county",
    "max_counties": "max_county",
    "max_cities": "max_city"}
CENSUS_GEOGRAPHY_TYPE_ALIASES = {"tract": "tracts",
    "block_group": "block_groups",
    "block": "blocks",
    "county": "counties"}


def load_config() -> dict:
    """Load and validate pipeline/config.yaml.

    Returns a dict with snake_case keys and Python-native values
    (list[str] for census_geography_years, Path for run_output_dir).
    """
    with open(CONFIG_FILE) as f:
        raw = yaml.safe_load(f)

    # study_area_type
    study_area_type = STUDY_AREA_TYPE_ALIASES.get(str(raw["study_area_type"]), str(raw["study_area_type"]))

    # census_geography_type
    census_geography_type = CENSUS_GEOGRAPHY_TYPE_ALIASES.get(
        str(raw["census_geography_type"]), str(raw["census_geography_type"]))

    # census_geography_years
    years = [str(y) for y in raw["census_geography_years"]]
    if census_geography_type in ("block_groups", "blocks") and "1980" in years:
        print(f"Warning: Skipping 1980 for census_geography_type={census_geography_type}. NHGIS does not publish 1980 block group or block boundary shapefiles.",
            file=sys.stderr)
        years = [y for y in years if y != "1980"]

    study_area_vintage = str(raw.get("study_area_vintage", "2020"))

    # other variables
    study_area_definition_geography_type = "places" if study_area_type == "max_city" else "counties"
    study_area_definition_geography_year = study_area_vintage
    study_area_source_file = None

    if study_area_type in ("cbsa", "max_city", "max_county"):
        source_pattern = f"list1_*{study_area_vintage}.xls"
        matches = sorted(glob.glob(str(REPO_ROOT / "data" / "raw" / "study_area_sources" / source_pattern)))
        if not matches:
            raise FileNotFoundError(f"No study area source file found for study_area_type={study_area_type!r}, study_area_vintage={study_area_vintage!r}.")
        study_area_source_file = matches[-1]
        study_area_definition_vintage = Path(study_area_source_file).stem.removeprefix("list1_")
    else:
        study_area_definition_vintage = study_area_vintage

    study_area_definition_geographies = (f"data/processed/census_geographies/{study_area_definition_geography_type}/{study_area_definition_geography_year}_{study_area_definition_geography_type}_*.gpkg")

    run_output_dir = REPO_ROOT / "outputs" / f"{census_geography_type}_in_{study_area_type}"

    return {"study_area_type": study_area_type,
        "census_geography_type": census_geography_type,
        "census_geography_years": years,
        "study_area_vintage": study_area_vintage,
        "study_area_definition_geography_type": study_area_definition_geography_type,
        "study_area_definition_geography_year": study_area_definition_geography_year,
        "study_area_source_file": study_area_source_file,
        "study_area_definition_vintage": study_area_definition_vintage,
        "study_area_definition_geographies": study_area_definition_geographies,
        "output_suffix": f"{study_area_type}_{census_geography_type}_{study_area_definition_vintage}",
        "run_output_dir": run_output_dir}


if __name__ == "__main__":
    import shlex

    cfg = load_config()
    exports = {**{k.upper(): str(v) for k, v in cfg.items() if v is not None},
        "CENSUS_GEOGRAPHY_YEARS": " ".join(cfg["census_geography_years"])}
    for key, value in exports.items():
        print(f"export {key}={shlex.quote(value)}")
