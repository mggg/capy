import json
from pathlib import Path

import pandas as pd
import typer

from capy_core.pipeline_filenames import format_definition_stem, parse_geography_name
from capy_core.utils import definitions


def parse_cbsa(config_loc: str) -> definitions.StudyArea:
    """Load a study area definition JSON and return a StudyArea object. Fills in optional fields (geometry, total_population) before parsing"""
    with open(config_loc) as f:
        data = json.load(f)

    if isinstance(data, str):
        data = json.loads(data)

    data.setdefault("geometry", None)
    data.setdefault("total_population", None)

    if hasattr(definitions.StudyArea, "model_validate"):
        return definitions.StudyArea.model_validate(data)
    return definitions.StudyArea.parse_obj(data)


def join_study_area_metadata(
    df: pd.DataFrame,
    definitions_dir: Path = Path("data/shared/processed/study_area_definitions"),
) -> pd.DataFrame:
    """Join study area metadata onto a raw metrics DataFrame.

    Reads the corresponding definition JSON for each row's filename and adds
    columns: definition_month_year, year, area_title, area_code,
    total_population_2020.
    """
    geography_identities = df["filename"].apply(parse_geography_name)
    definition_paths = geography_identities.apply(
        lambda geography_identity: (
            definitions_dir / f"{format_definition_stem(geography_identity.study_area)}.json"
        )
    )
    cbsa_infos = definition_paths.apply(parse_cbsa)
    df["definition_month_year"] = geography_identities.apply(
        lambda geography_identity: geography_identity.study_area.study_area_label
    )
    df["year"] = geography_identities.apply(
        lambda geography_identity: geography_identity.census_year
    )
    df["area_title"] = cbsa_infos.apply(lambda x: x.area_title)
    df["area_code"] = cbsa_infos.apply(lambda x: x.area_code)
    df["total_population_2020"] = cbsa_infos.apply(lambda x: x.total_population)

    return df


def main(filename: str, output: str):
    df = join_study_area_metadata(pd.read_csv(filename))
    df.to_csv(output, index=False)


if __name__ == "__main__":
    typer.run(main)
