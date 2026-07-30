"""
Load experiment configuration and execute the reusable pipeline stages in a
consistent order.  Replaces the control logic spread across resolve_config.py
and reproduce.sh.
"""
import glob
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULTS_PATH = _REPO_ROOT / "experiments" / "defaults.json"

_STUDY_AREA_ALIASES: dict[str, str] = {"counties": "county"}
_STUDY_AREA_TYPES: set[str] = {"cbsa", "county"}
_GEOGRAPHY_ALIASES: dict[str, str] = {
    "tract": "tracts", "block_group": "block_groups",
    "block": "blocks", "county": "counties",
}
_GEOGRAPHY_TYPES: set[str] = {"tracts", "block_groups", "blocks", "counties"}


# ── config loading ────────────────────────────────────────────────────────────

def load_json(path: Path | str) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def merge_config(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    return {**defaults, **overrides}


def _normalize(value: str, aliases: dict[str, str], valid: set[str], name: str) -> str:
    value = aliases.get(value, value)
    if value not in valid:
        raise ValueError(
            f"Unsupported {name}={value!r}. Valid values: {', '.join(sorted(valid))}"
        )
    return value


def validate_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Normalize, validate, and fill in derived fields. Returns the resolved config."""
    r = dict(cfg)

    r["study_area_type"] = _normalize(
        str(r["study_area_type"]), _STUDY_AREA_ALIASES, _STUDY_AREA_TYPES, "study_area_type"
    )
    r["census_geography_type"] = _normalize(
        str(r["census_geography_type"]), _GEOGRAPHY_ALIASES, _GEOGRAPHY_TYPES,
        "census_geography_type",
    )

    years = [str(y) for y in r["census_geography_years"]]
    if r["census_geography_type"] in ("block_groups", "blocks") and "1980" in years:
        print(
            f"Warning: skipping 1980 for census_geography_type={r['census_geography_type']} — "
            "NHGIS does not publish 1980 block group or block boundary shapefiles.",
            file=sys.stderr,
        )
        years = [y for y in years if y != "1980"]
    r["census_geography_years"] = years

    study_area_vintage = str(r.get("study_area_vintage", "2020"))
    r["study_area_vintage"] = study_area_vintage

    r["study_area_definition_geography_type"] = _normalize(
        str(r.get("study_area_definition_geography_type", "counties")),
        _GEOGRAPHY_ALIASES, _GEOGRAPHY_TYPES, "study_area_definition_geography_type",
    )
    r.setdefault("study_area_definition_geography_year", study_area_vintage)

    if r["study_area_type"] == "cbsa":
        if "study_area_source_file" not in r:
            pattern = r.get("study_area_source_pattern", f"list1_*_{study_area_vintage}.xls")
            matches = sorted(
                glob.glob(str(_REPO_ROOT / "data/raw/study_area_sources" / pattern))
            )
            if not matches:
                raise FileNotFoundError(
                    f"No study area source file matching {pattern!r} in "
                    "data/raw/study_area_sources/"
                )
            r["study_area_source_file"] = matches[-1]
        if "study_area_definition_vintage" not in r:
            stem = Path(r["study_area_source_file"]).stem
            r["study_area_definition_vintage"] = stem.removeprefix("list1_")
    else:
        r.setdefault("study_area_definition_vintage", study_area_vintage)

    def_year = r["study_area_definition_geography_year"]
    def_type = r["study_area_definition_geography_type"]
    r.setdefault(
        "study_area_definition_geographies",
        str(_REPO_ROOT / "data/processed/census_geographies" / f"{def_year}_{def_type}.gpkg"),
    )

    run_name = r.get("run_name") or r.get("name") or (
        f"{r['census_geography_type']}_in_{r['study_area_type']}"
    )
    r["run_name"] = run_name
    r.setdefault("run_output_dir", str(_REPO_ROOT / "outputs" / run_name))

    return r


def load_experiment_config(config_path: Path | str) -> dict[str, Any]:
    defaults = load_json(_DEFAULTS_PATH)
    overrides = load_json(config_path)
    return validate_config(merge_config(defaults, overrides))


# ── output directory ──────────────────────────────────────────────────────────

def prepare_output_directory(cfg: dict[str, Any]) -> Path:
    output_dir = Path(cfg["run_output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_resolved_config(cfg: dict[str, Any], output_dir: Path) -> None:
    record = {
        "start_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **cfg,
    }
    with open(output_dir / "run.log", "w") as f:
        json.dump(record, f, indent=2)


# ── subprocess helpers ────────────────────────────────────────────────────────

def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, cwd=_REPO_ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed (exit {result.returncode}): {' '.join(cmd)}")


def _run_capture(cmd: list[str]) -> str:
    result = subprocess.run(cmd, cwd=_REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {result.returncode}): {' '.join(cmd)}\n{result.stderr}"
        )
    return result.stdout


def _py(*args: str) -> list[str]:
    return ["poetry", "run", "python", *args]


def _rel(path: str) -> str:
    return str(Path(path).relative_to(_REPO_ROOT))


# ── pipeline stages ───────────────────────────────────────────────────────────

def run_download_stage(cfg: dict[str, Any]) -> None:
    geo_type = cfg["census_geography_type"]
    years = " ".join(cfg["census_geography_years"])

    _run(_py("pipeline/download/download_population_tables.py", "--level", geo_type, "--years", years))
    _run(_py("pipeline/download/download_geographies.py", "--level", geo_type, "--years", years))
    _run(_py("pipeline/preprocessing/census_geographies.py", "--level", geo_type, "--years", years))

    # Download definition geographies separately only when they differ from the
    # main geography type/year (avoids a redundant download in the common case).
    def_type = cfg["study_area_definition_geography_type"]
    def_year = cfg["study_area_definition_geography_year"]
    if def_type != geo_type or def_year not in cfg["census_geography_years"]:
        _run(_py("pipeline/download/download_population_tables.py", "--level", def_type, "--years", def_year))
        _run(_py("pipeline/download/download_geographies.py", "--level", def_type, "--years", def_year))
        _run(_py("pipeline/preprocessing/census_geographies.py", "--level", def_type, "--years", def_year))


def run_preprocessing_stage(cfg: dict[str, Any]) -> None:
    study_areas_cmd = _py(
        "pipeline/preprocessing/study_areas.py",
        "--definition-geographies", cfg["study_area_definition_geographies"],
        "--output-dir", "data/processed/study_area_definitions",
        "--study-area-type", cfg["study_area_type"],
        "--definition-vintage", cfg["study_area_definition_vintage"],
    )
    if cfg["study_area_type"] == "cbsa":
        study_areas_cmd += ["--filename", cfg["study_area_source_file"]]
    _run(study_areas_cmd)

    geo_type = cfg["census_geography_type"]
    study_area_type = cfg["study_area_type"]
    vintage = cfg["study_area_definition_vintage"]
    output_dir = Path(cfg["run_output_dir"])

    def _overlap(year: str) -> None:
        _run(_py(
            "pipeline/preprocessing/overlaps.py",
            f"data/processed/census_geographies/{year}_{geo_type}.gpkg",
            f"data/processed/study_area_definitions/{study_area_type}_*_{vintage}.gpkg",
            f"data/processed/clipped_geographies/{year}",
            "--census-geography-type", geo_type,
            "--census-geography-year", year,
            "--definition-vintage", vintage,
        ))

    with ThreadPoolExecutor() as pool:
        futures = [pool.submit(_overlap, y) for y in cfg["census_geography_years"]]
        for future in as_completed(futures):
            future.result()


def run_graph_stage(cfg: dict[str, Any]) -> None:
    geo_type = cfg["census_geography_type"]
    study_area_type = cfg["study_area_type"]
    vintage = cfg["study_area_definition_vintage"]

    geo_files: list[str] = []
    for year in cfg["census_geography_years"]:
        pattern = str(
            _REPO_ROOT / "data/processed/clipped_geographies" / year
            / f"{geo_type}_in_{study_area_type}_*_{year}_{vintage}_vintage.gpkg"
        )
        geo_files.extend(glob.glob(pattern))

    def _build_graph(geo_file: str) -> None:
        geo_rel = _rel(geo_file)
        year = Path(geo_rel).parent.name
        stem_name = Path(geo_rel).stem
        dual_dir = f"data/processed/dual_graphs/{year}"
        _run(_py("pipeline/graphs.py", geo_rel,
                 f"{dual_dir}/{stem_name}_orig.json",
                 f"{dual_dir}/{stem_name}_connected.json"))

    with ThreadPoolExecutor() as pool:
        futures = [pool.submit(_build_graph, geo_file) for geo_file in geo_files]
        for future in as_completed(futures):
            future.result()


def run_metrics_stage(cfg: dict[str, Any]) -> None:
    geo_type = cfg["census_geography_type"]
    study_area_type = cfg["study_area_type"]
    vintage = cfg["study_area_definition_vintage"]
    output_dir = Path(cfg["run_output_dir"])

    json_files: list[str] = []
    for year in cfg["census_geography_years"]:
        pattern = str(
            _REPO_ROOT / "data/processed/dual_graphs" / year
            / f"{geo_type}_in_{study_area_type}_*_{year}_{vintage}_vintage_connected.json"
        )
        json_files.extend(glob.glob(pattern))

    def _calculate_csv(output_file: Path, *groups: str) -> None:
        header = _run_capture(_py("pipeline/metrics.py", "", *groups, "--headers-only"))
        output_file.write_text(header)

        def _one(jf: str) -> str:
            return _run_capture(_py("pipeline/metrics.py", _rel(jf), *groups))

        with ThreadPoolExecutor() as pool:
            futures = [pool.submit(_one, jf) for jf in json_files]
            with open(output_file, "a") as f:
                for future in as_completed(futures):
                    f.write(future.result())

    _calculate_csv(output_dir / "white_black.csv", "BLACK", "WHITE", "TOTPOP")
    _calculate_csv(output_dir / "white_poc.csv", "POC", "WHITE", "TOTPOP")


def run_figures_stage(cfg: dict[str, Any]) -> None:
    geo_type = cfg["census_geography_type"]
    study_area_type = cfg["study_area_type"]
    run_output_dir = cfg["run_output_dir"]
    for metric in ("white_black", "white_poc"):
        _run(_py(
            "pipeline/visualization/generate_figures.py",
            "--filename", f"{run_output_dir}/{metric}.csv",
            "--prefix", f"{metric}_{study_area_type}_{geo_type}",
            "--geography-type", geo_type,
        ))


# ── entry point ───────────────────────────────────────────────────────────────

def run_experiment(config: str = "experiments/baseline/config.json") -> None:
    """Run the full pipeline for a given experiment config."""
    cfg = load_experiment_config(config)
    output_dir = prepare_output_directory(cfg)
    write_resolved_config(cfg, output_dir)
    run_download_stage(cfg)
    run_preprocessing_stage(cfg)
    run_graph_stage(cfg)
    run_metrics_stage(cfg)
    run_figures_stage(cfg)


if __name__ == "__main__":
    typer.run(run_experiment)
