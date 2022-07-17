import typer
import pandas as pd
import definitions
import json


def parse_cbsa(config_loc: str) -> definitions.CBSA:
    with open(config_loc) as f:
        data = json.load(f)

    return definitions.CBSA.parse_raw(data)

def main(filename: str, output: str):
    df = pd.read_csv(filename)
    cbsa_infos = df["filename"].apply(lambda x: "cbsas/defs/" + "_".join(x.split("/")[2].split("_")[:2]) + ".json").apply(parse_cbsa)

    df["year"] = df["filename"].apply(lambda x: x.split("/")[1])
    df["cbsa_title"] = cbsa_infos.apply(lambda x: x.cbsa_title)
    df["cbsa_code"] = cbsa_infos.apply(lambda x: x.cbsa_code)
    df["total_population"] = cbsa_infos.apply(lambda x: x.total_population)

    df.to_csv(output, index = False)


if __name__ == "__main__":
    typer.run(main)
