import pytest
import yaml

from capy_core.pipeline_config import build_geography_requests, load_config


def write_config(config_path, **settings):
    config = {
        "study_area_type": "county",
        "census_geography_type": "tracts",
        "census_geography_years": [2020],
        "study_area_source": None,
        "study_area_label": "march_2020",
    }
    config.update(settings)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config_path


@pytest.mark.parametrize("root_setting", [None, "../separate data", "absolute"])
def test_paths_resolve_from_config_and_root_not_working_directory(
    tmp_path, monkeypatch, root_setting
):
    config_path = tmp_path / "project" / "configs" / "run.yaml"
    expected_root = tmp_path / "project"
    if root_setting == "../separate data":
        expected_root = tmp_path / "project" / "separate data"
    elif root_setting == "absolute":
        expected_root = tmp_path / "absolute root"
        root_setting = str(expected_root)

    write_config(
        config_path,
        repo_root=root_setting,
        data_root="census data",
        output_root="results",
        figure_root=str(tmp_path / "absolute figures"),
        env_file="credentials.env",
        parallel_graph_workers=2,
    )
    monkeypatch.chdir(tmp_path)
    config = load_config(config_path.relative_to(tmp_path))

    assert config.repo_root_path == expected_root
    assert (
        config.raw_population_path
        == expected_root / "census data" / "raw" / "population"
    )
    assert (
        config.graphs_path
        == expected_root / "census data" / "processed" / "dual_graphs"
    )
    assert (
        config.run_output_path
        == expected_root / "results/tracts_in_county/march_2020/2020"
    )
    assert (
        config.figure_output_path
        == tmp_path / "absolute figures/tracts_in_county/march_2020/2020"
    )
    assert config.env_file_path == expected_root / "credentials.env"
    assert config.settings.parallel_graph_workers == 2


def test_omitted_root_and_execution_settings_use_documented_defaults(tmp_path):
    config_path = write_config(tmp_path / "config" / "run.yaml")
    config = load_config(config_path)

    assert config.repo_root_path == tmp_path
    assert config.data_root_path == tmp_path / "data/shared"
    assert config.output_root_path == tmp_path / "data/shared/outputs"
    assert config.figure_root_path == tmp_path / "figures/baseline"
    assert config.env_file_path == tmp_path / ".env"
    assert config.settings.parallel_graph_workers == 6
    assert config.study_area_source_path is None
    assert config.definition_geography_type == "counties"


@pytest.mark.parametrize("absolute_source", [False, True])
def test_explicit_csv_source_and_label_are_independent_of_filename(
    tmp_path, absolute_source
):
    source_path = tmp_path / "metro membership.csv"
    source_path.write_text("CBSA Code,CBSA Title\n", encoding="utf-8")
    config_path = write_config(
        tmp_path / "configs" / "run.yaml",
        study_area_type="max_city",
        study_area_source=str(source_path) if absolute_source else source_path.name,
        data_root="elsewhere",
        study_area_label="chosen_definition",
    )
    config = load_config(config_path)

    assert config.study_area_source_path == source_path
    assert (
        config.run_relative_path.as_posix()
        == "tracts_in_max_city/chosen_definition/2020"
    )
    assert config.definition_geography_type == "places"


@pytest.mark.parametrize(
    "geography, years, study_area_type, expected, year_label",
    [
        (
            "counties",
            [2020, 2010],
            "county",
            [(2020, "counties"), (2010, "counties")],
            "2010_2020",
        ),
        (
            "blocks",
            [1980, 2020],
            "county",
            [(2020, "blocks"), (2020, "counties")],
            "2020",
        ),
        (
            "tracts",
            [2020, 1980],
            "max_city",
            [(2020, "tracts"), (1980, "tracts"), (2020, "counties"), (2020, "places")],
            "1980_2020",
        ),
    ],
)
def test_geography_requests_include_definition_inputs_once(
    tmp_path, geography, years, study_area_type, expected, year_label
):
    source_path = tmp_path / "source.csv"
    source_path.touch()
    config = load_config(
        write_config(
            tmp_path / "configs" / "run.yaml",
            study_area_type=study_area_type,
            study_area_source=source_path.name
            if study_area_type == "max_city"
            else None,
            census_geography_type=geography,
            census_geography_years=years,
        )
    )

    assert [
        (request.year, request.geography)
        for request in build_geography_requests(config)
    ] == expected
    assert config.settings.census_geography_years == tuple(years)
    assert config.run_relative_path.parts[-1] == year_label


# NOTE: AI assisted in generating these test cases. Mainly in finding missing cases.
@pytest.mark.parametrize(
    "settings, message",
    [
        ({"study_area_type": []}, "study_area_type"),
        ({"census_geography_type": "places"}, "census_geography_type"),
        ({"census_geography_years": "2020"}, "nonempty list"),
        ({"census_geography_years": []}, "nonempty list"),
        ({"census_geography_years": [True]}, "Unsupported census geography year"),
        ({"census_geography_years": [2020, 2020]}, "Duplicate census geography year"),
        (
            {"census_geography_type": "blocks", "census_geography_years": [1980]},
            "boundary years",
        ),
        ({"study_area_vintage": "2020"}, "study_area_vintage"),
        ({"parallel_graph_workers": True}, "parallel_graph_workers"),
        ({"parallel_graph_workers": 0}, "parallel_graph_workers"),
        ({"repo_root": " "}, "repo_root"),
        ({"data_root": None}, "data_root"),
        ({"study_area_label": "../escape"}, "study_area_label"),
        ({"study_area_label": 2020}, "study_area_label"),
        ({"study_area_source": "source.csv"}, "county mode"),
        ({"study_area_type": "cbsa"}, "study_area_source"),
        ({"study_area_type": "cbsa", "study_area_source": "source.xls"}, "CSV path"),
        (
            {
                "study_area_type": "max_city",
                "study_area_source": "source.csv",
                "study_area_vintage": 2010,
            },
            "requires",
        ),
        ({"workers": 6}, "Unknown fields"),
    ],
)
def test_invalid_settings_fail_before_source_access(tmp_path, settings, message):
    config_path = write_config(tmp_path / "configs" / "run.yaml", **settings)
    with pytest.raises(ValueError, match=message):
        load_config(config_path)


def test_missing_source_does_not_fall_back_to_another_csv(tmp_path):
    (tmp_path / "list1_march_2020.csv").touch()
    config_path = write_config(
        tmp_path / "configs" / "run.yaml",
        study_area_type="cbsa",
        study_area_source="chosen.csv",
    )
    with pytest.raises(FileNotFoundError, match="chosen.csv"):
        load_config(config_path)


@pytest.mark.parametrize(
    "contents, message",
    [
        ("", "Config YAML must be a mapping"),
        ("{}", "Missing required fields"),
        ("study_area_type: [", "Error parsing YAML"),
    ],
)
def test_invalid_config_file_reports_its_path(tmp_path, contents, message):
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message) as error:
        load_config(config_path)

    assert str(config_path) in str(error.value)


def test_missing_config_is_reported_without_creating_it(tmp_path):
    config_path = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError, match="Config file not found") as error:
        load_config(config_path)

    assert str(config_path) in str(error.value)
    assert not config_path.exists()
