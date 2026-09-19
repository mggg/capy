import json

import pandas as pd

from capy_core.process_results import (
    join_study_area_metadata,
    parse_cbsa,
)


def test_metadata_lookup_uses_complete_label_and_filename_year(tmp_path):
    definition = {
        "area_code": "01001",
        "area_title": "Example County",
        "component_counties_fips": ["01001"],
        "total_population": 100,
    }
    (tmp_path / "county_01001_region_in_1990_label.json").write_text(json.dumps(definition))
    metrics = pd.DataFrame(
        {
            "filename": [
                "parent_in_name/2020/tracts_in_county_01001_1980_region_in_1990_label_vintage_orig.json"
            ]
        }
    )

    result = join_study_area_metadata(metrics, tmp_path)

    assert result.loc[0, "area_code"] == "01001"
    assert result.loc[0, "year"] == 1980
    assert result.loc[0, "definition_month_year"] == "region_in_1990_label"
    assert result.loc[0, "total_population_2020"] == 100


def test_parse_cbsa_accepts_json_encoded_definition(tmp_path):
    path = tmp_path / "cbsa_39460_march_2020.json"
    path.write_text(
        json.dumps(
            json.dumps(
                {
                    "area_code": "39460",
                    "area_title": "Punta Gorda, FL",
                    "component_counties_fips": ["12015"],
                    "total_population": 186847,
                }
            )
        )
    )

    cbsa = parse_cbsa(str(path))

    assert cbsa.area_code == "39460"
    assert cbsa.area_title == "Punta Gorda, FL"
