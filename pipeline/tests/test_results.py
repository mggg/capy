import json

from pipeline.process_results import definition_json_for_output, output_name_parts, parse_cbsa


def test_output_name_parts_for_configured_study_area_layout():
    filename = (
        "dual_graphs/2020/"
        "tracts_in_cbsa_39460_2020_march_2020_vintage_connected.json"
    )

    assert output_name_parts(filename) == ("cbsa_39460", "2020", "march_2020")


def test_definition_json_for_configured_study_area_layout():
    filename = (
        "dual_graphs/1980/"
        "tracts_in_cbsa_35620_1980_march_2020_vintage_orig.json"
    )

    assert (
        definition_json_for_output(filename)
        == "data/processed/study_area_definitions/cbsa_35620_march_2020.json"
    )


def test_output_name_parts_for_legacy_cbsa_layout():
    filename = "dual_graphs/2020/186847_39460_march_2020_cbsa_tracts_connected.json"

    assert output_name_parts(filename) == ("cbsa_39460", "2020", "march_2020")


def test_parse_cbsa_accepts_json_encoded_definition(tmp_path):
    path = tmp_path / "cbsa_39460_march_2020.json"
    path.write_text(
        json.dumps(
            json.dumps(
                {
                    "cbsa_code": "39460",
                    "cbsa_title": "Punta Gorda, FL",
                    "component_counties_fips": ["12015"],
                    "total_population": 186847,
                }
            )
        )
    )

    cbsa = parse_cbsa(str(path))

    assert cbsa.cbsa_code == "39460"
    assert cbsa.cbsa_title == "Punta Gorda, FL"
