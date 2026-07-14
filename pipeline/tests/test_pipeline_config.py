import os
import subprocess


def source_config(command: str, extra_env: dict | None = None):
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("STUDY_AREA") or name.startswith("CENSUS_GEOGRAPHY"):
            env.pop(name)
    env["STUDY_AREA_SOURCE_FILE"] = "data/interim/study_area_sources/list1_march_2020.xls"
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        ["bash", "-c", f". scripts/pipeline_config.sh; {command}"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_cbsa_definition_geography_defaults_to_counties():
    result = source_config('printf "%s" "${STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE}"')

    assert result.returncode == 0
    assert result.stdout == "counties"


def test_cbsa_is_not_a_definition_geography_type():
    result = source_config(
        "true",
        {"STUDY_AREA_DEFINITION_GEOGRAPHY_TYPE": "cbsa"},
    )

    assert result.returncode == 1
    assert "For STUDY_AREA_TYPE=cbsa, use counties" in result.stderr
