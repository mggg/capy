import json
from pathlib import Path

import pandas as pd
import typer

try:
    from . import definitions
except ImportError:
    import definitions


def parse_cbsa(config_loc: str) -> definitions.CBSA:
    with open(config_loc) as f:
        data = json.load(f)

    if isinstance(data, str):
        data = json.loads(data)

    data.setdefault("geometry", None)
    data.setdefault("total_population", None)

    if hasattr(definitions.CBSA, "model_validate"):
        return definitions.CBSA.model_validate(data)
    return definitions.CBSA.parse_obj(data)


def _strip_graph_suffix(filename: str) -> str:
    output_stem = Path(filename).stem
    for suffix in ("_connected", "_orig"):
        if output_stem.endswith(suffix):
            return output_stem.removesuffix(suffix)
    return output_stem


def output_name_parts(filename: str):
    output_stem = _strip_graph_suffix(filename)

    if "_in_" in output_stem and output_stem.endswith("_vintage"):
        output_stem = output_stem.removesuffix("_vintage")
        _, study_area_and_dates = output_stem.split("_in_", 1)
        study_area_identity, geography_year, month, vintage_year = (
            study_area_and_dates.rsplit("_", 3)
        )
        return study_area_identity, geography_year, f"{month}_{vintage_year}"

    geography_year = Path(filename).parent.name
    tokens = output_stem.split("_")
    if len(tokens) < 4:
        raise ValueError(f"Cannot parse output filename: {filename}")
    _, study_area_code, month, vintage_year = tokens[:4]
    return f"cbsa_{study_area_code}", geography_year, f"{month}_{vintage_year}"


def definition_json_for_output(filename: str) -> str:
    output_stem = _strip_graph_suffix(filename)
    if "_in_" in output_stem and output_stem.endswith("_vintage"):
        study_area_identity, _, definition_vintage = output_name_parts(filename)
        definition_stem = f"{study_area_identity}_{definition_vintage}"
        return f"study_areas/definitions/{definition_stem}.json"

    tokens = output_stem.split("_")
    return f"cbsas/defs/{'_'.join(tokens[:4])}.json"


def enrich_metrics(df: pd.DataFrame) -> pd.DataFrame:
    cbsa_infos = df["filename"].apply(definition_json_for_output).apply(parse_cbsa)
    df["definition_month_year"] = df["filename"].apply(
        lambda x: output_name_parts(x)[2]
    )
    df["year"] = df["filename"].apply(lambda x: int(output_name_parts(x)[1]))
    df["cbsa_title"] = cbsa_infos.apply(lambda x: x.cbsa_title)
    df["cbsa_code"] = cbsa_infos.apply(lambda x: x.cbsa_code)
    df["total_population_2020"] = cbsa_infos.apply(lambda x: x.total_population)

    return df


def main(filename: str, output: str):
    df = enrich_metrics(pd.read_csv(filename))
    df.to_csv(output, index=False)


if __name__ == "__main__":
    typer.run(main)
