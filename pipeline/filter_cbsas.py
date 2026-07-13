import sys
from pathlib import Path

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.build_study_areas import main as build_study_areas


def main(
    filename: str = "study_area_sources/list1_march_2020.xls",
    definition_tracts: str = "census_geographies/2020_tracts.shp",
    output_dir: str = "study_areas/definitions",
):
    build_study_areas(
        filename=filename,
        definition_geographies=definition_tracts,
        output_dir=output_dir,
        study_area_type="cbsa",
    )


if __name__ == "__main__":
    typer.run(main)
