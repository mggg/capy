from census.core import CensusException

import pandas as pd

from pipeline.download_population_tables import LEVELS, fetch_census_state_rows, geoid
from pipeline.download_population_tables import NHGIS_EXTRACTS_DIR


class FakeTable:
    def __init__(self, fail_state_query=False):
        self.calls = []
        self.fail_state_query = fail_state_query

    def get(self, variables, geo):
        self.calls.append((tuple(variables), dict(geo)))
        if self.fail_state_query and len(self.calls) == 1:
            raise CensusException("unsupported geography")
        if geo["for"] == "county:*":
            return [{"county": "001"}, {"county": "003"}]
        return [{"NAME": "row"}]


def test_block_groups_use_state_wide_census_query():
    table = FakeTable()

    rows = fetch_census_state_rows(
        table,
        ["NAME", "P1_001N"],
        LEVELS["block_groups"],
        "01",
        progress=False,
    )

    assert rows == [{"NAME": "row"}]
    assert table.calls == [
        (
            ("NAME", "P1_001N"),
            {"for": "block group:*", "in": "state:01 county:* tract:*"},
        )
    ]


def test_block_groups_fall_back_to_county_queries():
    table = FakeTable(fail_state_query=True)

    rows = fetch_census_state_rows(
        table,
        ["NAME", "P1_001N"],
        LEVELS["block_groups"],
        "01",
        progress=False,
    )

    assert rows == [{"NAME": "row"}, {"NAME": "row"}]
    assert table.calls == [
        (
            ("NAME", "P1_001N"),
            {"for": "block group:*", "in": "state:01 county:* tract:*"},
        ),
        (("NAME",), {"for": "county:*", "in": "state:01"}),
        (
            ("NAME", "P1_001N"),
            {"for": "block group:*", "in": "state:01 county:001 tract:*"},
        ),
        (
            ("NAME", "P1_001N"),
            {"for": "block group:*", "in": "state:01 county:003 tract:*"},
        ),
    ]


def test_blocks_still_use_county_scoped_queries():
    table = FakeTable()

    fetch_census_state_rows(
        table,
        ["NAME", "P1_001N"],
        LEVELS["blocks"],
        "01",
        progress=False,
    )

    assert table.calls == [
        (("NAME",), {"for": "county:*", "in": "state:01"}),
        (
            ("NAME", "P1_001N"),
            {"for": "block:*", "in": "state:01 county:001 tract:*"},
        ),
        (
            ("NAME", "P1_001N"),
            {"for": "block:*", "in": "state:01 county:003 tract:*"},
        ),
    ]


def test_2000_geoid_preserves_integer_and_decimal_tracts():
    df = pd.DataFrame(
        {
            "state": ["06", "06"],
            "county": ["053", "053"],
            "tract": ["000104", "0104"],
            "block group": ["1", "1"],
        }
    )

    assert geoid(
        df,
        ("state", "county", "tract", "block group"),
        2000,
    ).tolist() == ["060530001041", "060530104001"]


def test_population_nhgis_extracts_default_is_under_population_raw_dir():
    assert str(NHGIS_EXTRACTS_DIR) == "census_raw/population/ipums_population_extracts"
