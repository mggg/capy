"""Processing stages must reject overlapping inputs and outputs before deleting files."""

from pathlib import Path

import pytest
from capy_core.assign_study_areas.run_assignment import assign_study_areas
from capy_core.join_geographies.join_tables import join_geography_tables
from capy_core.pipeline_config import PipelineConfig
from capy_core.process_population.process_tables import process_population_tables


@pytest.mark.parametrize(
    "run_stage,output_setting",
    [
        (process_population_tables, "processed_population_directory"),
        (join_geography_tables, "joined_geography_directory"),
        (assign_study_areas, "study_area_directory"),
    ],
)
@pytest.mark.parametrize("overlap", ["equal", "inside_input", "contains_input", "symlink"])
def test_overlapping_stage_directories_fail_before_cleanup(
    tmp_path, monkeypatch, run_stage, output_setting, overlap
):
    repository_root = tmp_path / "repository"
    raw_directory = repository_root / "inputs/raw"
    raw_directory.mkdir(parents=True)
    sentinel_path = raw_directory / "processing_summary.csv"
    sentinel_path.write_text("preserve input data")
    output_directory = Path("inputs/raw")

    if overlap == "inside_input":
        output_directory /= "derived"
    elif overlap == "contains_input":
        output_directory = Path("inputs")
    elif overlap == "symlink":
        output_directory = repository_root / "raw_alias"

        try:
            output_directory.symlink_to(raw_directory, target_is_directory=True)
        except OSError as error:
            if getattr(error, "winerror", None) != 1314:
                raise

            pytest.skip("This Windows account lacks permission to create symlinks")

    config = PipelineConfig(
        raw_data_directory=Path("inputs/raw"), **{output_setting: output_directory}
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="must be separate"):
        run_stage(config, repository_root)

    assert sentinel_path.read_text() == "preserve input data"
