"""Check exact source evidence before classifying a missing 1990 block as empty."""

from zipfile import ZipFile

import pandas as pd
import pytest
from capy_core.join_geographies import read_1990_zero_blocks


def prepare_california_references(tmp_path, monkeypatch):
    """Supply one real ZIP member inventory and small stand-ins for its DBF tables."""
    for disc_number in range(1, 11):
        with ZipFile(tmp_path / f"disc{disc_number}.zip", "w") as archive:
            if disc_number == 10:
                archive.writestr("STF1BZCA.DBF", b"DBF reader is replaced in this test")

    zero_reference_df = pd.DataFrame(
        {
            "SUMLEV": ["100"],
            "GEOCOMP": ["00"],
            "STATEFP": ["06"],
            "CNTY": ["113"],
            "TRACTBNA": ["9901"],
            "BLCK": ["001"],
            "POP100": [0],
            "HU100": [0],
        }
    )
    pl_reference_df = pd.concat([zero_reference_df] * 4, ignore_index=True)
    pl_reference_df["SUMLEV"] = "750"
    pl_reference_df["BLCK"] = ["002A", "002A", "003", "004"]
    pl_reference_df["POP100"] = pl_reference_df["P001_0001"] = [0, 0, 2, 0]
    pl_reference_df["HU100"] = pl_reference_df["H001_0001"] = [0, 0, 1, 1]

    def read_reference(filename, **kwargs):
        if str(filename).endswith("pl9417ca.dbf"):
            return pl_reference_df.copy()

        assert str(filename).endswith("disc10.zip!STF1BZCA.DBF")

        return zero_reference_df.copy()

    monkeypatch.setattr(read_1990_zero_blocks.gpd, "read_file", read_reference)

    return zero_reference_df, pl_reference_df


def test_zero_reference_combines_sources_without_treating_population_or_housing_as_empty(
    tmp_path, monkeypatch
):
    prepare_california_references(tmp_path, monkeypatch)

    block_ids = read_1990_zero_blocks.read_1990_zero_population_block_ids(tmp_path, "06")

    assert block_ids == {"06113990100001", "06113990100002A"}


def test_zero_reference_rejects_conflicting_duplicate_pl_counts(tmp_path, monkeypatch):
    _, pl_reference_df = prepare_california_references(tmp_path, monkeypatch)
    pl_reference_df.loc[1, ["POP100", "P001_0001"]] = 2

    with pytest.raises(ValueError, match="conflicting counts"):
        read_1990_zero_blocks.read_1990_zero_population_block_ids(tmp_path, "06")


def test_zero_reference_rejects_nonzero_stf1b_geographic_zero_record(tmp_path, monkeypatch):
    zero_reference_df, _ = prepare_california_references(tmp_path, monkeypatch)
    zero_reference_df.loc[0, "POP100"] = 1

    with pytest.raises(ValueError, match="nonzero counts"):
        read_1990_zero_blocks.read_1990_zero_population_block_ids(tmp_path, "06")


def test_queens_conflicting_zero_reference_does_not_erase_106_residents(tmp_path, monkeypatch):
    import geopandas as gpd
    from capy_core.join_geographies.join_population import (
        PopulationBoundaryJoin,
        apply_1990_zero_block_evidence,
    )

    for disc_number in range(1, 11):
        with ZipFile(tmp_path / f"disc{disc_number}.zip", "w") as archive:
            if disc_number == 2:
                archive.writestr("STF1BZNY.DBF", b"DBF reader replaced")

    zero_reference_df = pd.DataFrame(
        {
            "SUMLEV": ["100"],
            "GEOCOMP": ["00"],
            "STATEFP": ["36"],
            "CNTY": ["081"],
            "TRACTBNA": ["077398"],
            "BLCK": ["104"],
            "POP100": [0],
            "HU100": [0],
        }
    )
    monkeypatch.setattr(
        read_1990_zero_blocks.gpd, "read_file", lambda *args, **kwargs: zero_reference_df.copy()
    )

    zero_population_block_ids = read_1990_zero_blocks.read_1990_zero_population_block_ids(
        tmp_path, "36"
    )

    assert "36081077398104" not in zero_population_block_ids

    result = PopulationBoundaryJoin(
        gpd.GeoDataFrame({"BOUNDARY_CENSUS_ID": ["36081077398104"], "TOTPOP": [106]}),
        pd.DataFrame(),
        gpd.GeoDataFrame(
            {
                "BOUNDARY_CENSUS_ID": ["36081000100101"],
                "EXCLUSION_REASON": ["unresolved_correspondence"],
                "KNOWN_TOTAL_POPULATION": pd.Series([pd.NA], dtype="Int64"),
            }
        ),
    )

    original_matched_df = result.matched_geography_df.copy()
    original_unmatched_df = result.unmatched_boundaries_df.copy()
    classified_result = apply_1990_zero_block_evidence(
        result, zero_population_block_ids | {"36081000100101"}
    )
    assert classified_result.unmatched_boundaries_df.KNOWN_TOTAL_POPULATION.tolist() == [0]

    assert classified_result.matched_geography_df.TOTPOP.tolist() == [106]
    assert (
        "conflicting geographic-zero"
        in classified_result.matched_geography_df.GEOGRAPHY_NOTE.iloc[0]
    )
    assert classified_result.unmatched_population_df is result.unmatched_population_df
    pd.testing.assert_frame_equal(result.matched_geography_df, original_matched_df)
    pd.testing.assert_frame_equal(result.unmatched_boundaries_df, original_unmatched_df)

    with pytest.raises(ValueError, match="contradicts"):
        apply_1990_zero_block_evidence(result, {"36081077398104"})

    pd.testing.assert_frame_equal(result.matched_geography_df, original_matched_df)
    pd.testing.assert_frame_equal(result.unmatched_boundaries_df, original_unmatched_df)
