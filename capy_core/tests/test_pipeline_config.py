import pytest
import yaml

import capy_core.config as config_module
from capy_core.config import load_config


def _load_with_study_area_type(tmp_path, study_area_type):
    """Write a minimal config.yaml and a fake source file, then call load_config()."""
    config_yaml = tmp_path / "config.yaml"
    config_yaml.write_text(yaml.dump({
        "study_area_type": study_area_type,
        "census_geography_type": "tracts",
        "census_geography_years": [2020],
        "study_area_vintage": "2020",
    }))

    # Provide a fake source file so load_config doesn't raise FileNotFoundError
    source_dir = tmp_path / "data" / "shared" / "raw" / "study_area_sources"
    source_dir.mkdir(parents=True)
    (source_dir / "list1_march_2020.xls").touch()

    return config_module, config_yaml, tmp_path


def test_cbsa_definition_geography_defaults_to_counties(tmp_path, monkeypatch):
    mod, config_yaml, repo_root = _load_with_study_area_type(tmp_path, "cbsa")
    monkeypatch.setattr(mod, "CONFIG_FILE", config_yaml)
    monkeypatch.setattr(mod, "REPO_ROOT", repo_root)

    cfg = load_config()

    assert cfg["study_area_definition_geography_type"] == "counties"


def test_max_city_definition_geography_is_places(tmp_path, monkeypatch):
    """study_area_type=max_city must use 'places' as definition geography, never 'cbsa'."""
    mod, config_yaml, repo_root = _load_with_study_area_type(tmp_path, "max_city")
    monkeypatch.setattr(mod, "CONFIG_FILE", config_yaml)
    monkeypatch.setattr(mod, "REPO_ROOT", repo_root)

    cfg = load_config()

    assert cfg["study_area_definition_geography_type"] == "places"
    assert cfg["study_area_definition_geography_type"] != "cbsa"
