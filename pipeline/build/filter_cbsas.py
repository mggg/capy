import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.build.build_study_areas import main as build_study_areas


def main(
    filename: str = "data/interim/study_area_sources/list1_march_2020.xls",
    definition_tracts: str = "data/interim/census_geographies/2020_tracts.shp",
    output_dir: str = "data/interim/study_areas/definitions",
):
    build_study_areas(
        filename=filename,
        definition_geographies=definition_tracts,
        output_dir=output_dir,
        study_area_type="cbsa",
    )


if __name__ == "__main__":
    typer.run(main)
