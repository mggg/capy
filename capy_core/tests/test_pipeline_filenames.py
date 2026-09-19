from pathlib import Path

import pytest

from capy_core.pipeline_filenames import (
    GeographyFileIdentity,
    StudyAreaIdentity,
    format_definition_stem,
    format_geography_stem,
    format_graph_name,
    parse_definition_name,
    parse_geography_name,
)


@pytest.mark.parametrize(
    "study_area_type, area_code, label, geography",
    [
        ("cbsa", "10180", "march_2020", "tracts"),
        ("county", "01001", "2020", "block_groups"),
        ("max_county", "01001", "custom_in_1990_region", "blocks"),
        ("max_city", "0100100", "region_vintage_orig", "counties"),
    ],
)
def test_pipeline_filenames_round_trip_without_using_parent_directory(
    study_area_type, area_code, label, geography
):
    parent = Path("parent_in_name") / "wrong_year"
    identity = StudyAreaIdentity(study_area_type, area_code, label)
    geography_identity = GeographyFileIdentity(identity, geography, 2010)
    definition_stem = f"{study_area_type}_{area_code}_{label}"
    geography_stem = f"{geography}_in_{study_area_type}_{area_code}_2010_{label}_vintage"

    assert format_definition_stem(identity) == definition_stem
    assert format_geography_stem(geography_identity) == geography_stem
    for extension in ("json", "gpkg"):
        assert parse_definition_name(parent / f"{definition_stem}.{extension}") == identity

    assert parse_geography_name(parent / f"{geography_stem}.gpkg") == geography_identity
    for variant in ("orig", "connected"):
        graph_name = f"{geography_stem}_{variant}.json"
        assert format_graph_name(geography_identity, variant) == graph_name
        assert parse_geography_name(parent / graph_name) == geography_identity


@pytest.mark.parametrize(
    "filename",
    [
        "186847_39460_march_2020_cbsa_tracts_connected.json",
        "tracts_in_cbsa_12345_2020.gpkg",
        "tracts_in_cbsa_12345_2020_label_vintage_modified.json",
        "places_in_cbsa_12345_2020_label_vintage.gpkg",
        "tracts_in_cbsa_12345_2021_label_vintage.gpkg",
        "tracts_in_cbsa_12345_2020_label.with.dots_vintage.gpkg",
    ],
)
def test_rejects_unsupported_geography_names(filename):
    with pytest.raises(ValueError):
        parse_geography_name(filename)


@pytest.mark.parametrize(
    "filename",
    ["county_abc_label.json", "counties_01001_label.gpkg", "cbsa_10180_.json", "cbsa_10180_a.txt"],
)
def test_rejects_invalid_definition_names(filename):
    with pytest.raises(ValueError):
        parse_definition_name(filename)


def test_formatters_reject_invalid_identity_and_variant():
    with pytest.raises(ValueError, match="code"):
        format_definition_stem(StudyAreaIdentity("county", 1001, "2020"))

    identity = StudyAreaIdentity("county", "01001", "2020")
    with pytest.raises(ValueError, match="year"):
        format_geography_stem(GeographyFileIdentity(identity, "tracts", True))

    with pytest.raises(ValueError, match="variant"):
        format_graph_name(GeographyFileIdentity(identity, "tracts", 2020), "modified")
