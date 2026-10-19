from pathlib import Path

import pandas as pd
import pytest

from capy_core.preprocessing.population_tables import (
    load_population_table,
    parse_nhgis_1980_population,
    parse_population_counts,
)


@pytest.mark.parametrize("year", [2010, "20xx", None])
def test_population_file_rejects_rows_from_a_different_census_year(tmp_path, year):
    pd.DataFrame({"YEAR": [year], "state": ["01"], "county": ["001"],
                  "NH_WHITE": [1], "NH_BLACK": [1], "TOTPOP": [2]}).to_csv(
        tmp_path / "census_2020_counties.csv", index=False
    )
    with pytest.raises(ValueError, match="2020"):
        load_population_table(2020, tmp_path, "counties")


def test_population_counts_preserve_index_and_int64_limit():
    counts = parse_population_counts(
        pd.Series(["0", "12", str(2**63 - 1)], index=[4, 8, 9]),
        source=Path("population.csv"),
        column="TOTPOP",
    )

    assert counts.tolist() == [0, 12, 2**63 - 1]
    assert counts.index.tolist() == [4, 8, 9]
    assert counts.dtype == "int64"


@pytest.mark.parametrize("value", [None, "bad", "1.5", "inf", "-1", str(2**63)])
def test_invalid_population_counts_identify_the_source(value):
    with pytest.raises(ValueError, match=r"population.csv: TOTPOP"):
        parse_population_counts(
            pd.Series([value]), source=Path("population.csv"), column="TOTPOP"
        )


def build_1980_population_table(
    suffixes: tuple[str, ...], rows: int = 1
) -> pd.DataFrame:
    """Build synthetic rows with the complete STF1 NT7/NT9B column layout.

    Args:
        suffixes (tuple[str, ...]): Geographic component codes to include.
        rows (int, optional): Number of records. Defaults to 1.

    Returns:
        pd.DataFrame: String identifiers and counts, with zero counts in every race cell.
    """
    return pd.DataFrame(
        {
            "GISJOIN": [f"G01000{index + 1}0" for index in range(rows)],
            "STATEA": ["01"] * rows,
            "COUNTYA": ["001"] * rows,
            **{
                f"{base}{suffix}{index:03d}": ["0"] * rows
                for suffix in suffixes
                for base, cell_count in (("C9D", 15), ("C9G", 4))
                for index in range(1, cell_count + 1)
            },
        }
    )


def test_1980_concatenated_sources_preserve_absent_components_and_layouts():
    source_population_dfs = []
    for suffix, source_file in (
        ("AA", "urban.csv"),
        ("AB", "rural.csv"),
        ("", "total.csv"),
    ):
        suffixes = ("AA", "AB") if suffix else ("",)
        source_population_df = build_1980_population_table(suffixes, rows=2)
        source_population_df["NHGIS_SOURCE_FILE"] = source_file
        if suffix:
            absent_suffix = "AB" if suffix == "AA" else "AA"
            columns = [
                column
                for column in source_population_df
                if column[3:-3] == absent_suffix
            ]
            source_population_df[columns] = None
        source_population_df[f"C9D{suffix}001"] = ["10", "20"]
        source_population_df[f"C9D{suffix}002"] = ["3", "7"]
        source_population_df[f"C9D{suffix}003"] = ["1", "2"]
        source_population_df[f"C9G{suffix}001"] = ["1", "2"]
        source_population_df[f"C9G{suffix}002"] = ["0", "1"]
        source_population_dfs.append(source_population_df)
    source_population_df = pd.concat(source_population_dfs, ignore_index=True)
    original_population_df = source_population_df.copy(deep=True)

    population_df = parse_nhgis_1980_population(source_population_df, Path("1980.csv"))

    assert population_df[["WHITE", "BLACK", "TOTPOP"]].values.tolist() == [
        [9, 3, 14],
        [18, 6, 29],
        [9, 3, 14],
        [18, 6, 29],
        [9, 3, 14],
        [18, 6, 29],
    ]
    pd.testing.assert_frame_equal(source_population_df, original_population_df)
    source_population_df.loc[0, "C9DAA003"] = None
    with pytest.raises(ValueError, match="urban.csv: C9DAA003"):
        parse_nhgis_1980_population(source_population_df, Path("1980.csv"))


def test_1980_urban_rural_rows_include_absent_and_zero_population_components():
    source_population_df = build_1980_population_table(("AA", "AB"), rows=4)
    for suffix, white, black, other, hispanic_white, hispanic_black in (
        ("AA", "10", "3", "1", "1", "0"),
        ("AB", "20", "7", "2", "2", "1"),
    ):
        source_population_df[f"C9D{suffix}001"] = white
        source_population_df[f"C9D{suffix}002"] = black
        source_population_df[f"C9D{suffix}003"] = other
        source_population_df[f"C9G{suffix}001"] = hispanic_white
        source_population_df[f"C9G{suffix}002"] = hispanic_black
    for row, suffix in ((0, "AB"), (1, "AA")):
        columns = [column for column in source_population_df if column[3:-3] == suffix]
        source_population_df.loc[row, columns] = None
    count_columns = [
        column for column in source_population_df if column.startswith("C9")
    ]
    source_population_df.loc[3, count_columns] = "0"
    original_population_df = source_population_df.copy(deep=True)

    population_df = parse_nhgis_1980_population(source_population_df, Path("1980.csv"))

    assert population_df[["WHITE", "BLACK", "TOTPOP"]].values.tolist() == [
        [9, 3, 14],
        [18, 6, 29],
        [27, 9, 43],
        [0, 0, 0],
    ]
    pd.testing.assert_frame_equal(source_population_df, original_population_df)


@pytest.mark.parametrize("suffixes", [("",), ("AA", "AB")])
def test_1980_rejects_negative_non_hispanic_counts_within_each_component(suffixes):
    source_population_df = build_1980_population_table(suffixes)
    source_population_df[f"C9G{suffixes[0]}001"] = "1"
    if len(suffixes) == 2:
        # Another component's White population must not mask the invalid subtraction.
        source_population_df["C9DAB001"] = "20"
    with pytest.raises(ValueError, match="WHITE"):
        parse_nhgis_1980_population(source_population_df, Path("1980.csv"))


@pytest.mark.parametrize("column", ["C9DAA001", "C9DAB015", "C9GAB004"])
def test_1980_requires_complete_component_columns(column):
    source_population_df = build_1980_population_table(("AA", "AB"))
    with pytest.raises(ValueError, match=column):
        parse_nhgis_1980_population(
            source_population_df.drop(columns=column), Path("1980.csv")
        )


@pytest.mark.parametrize("column", ["C9DAA003", "C9GAB004"])
def test_1980_rejects_partially_missing_components(column):
    source_population_df = build_1980_population_table(("AA", "AB"))
    source_population_df[column] = None
    with pytest.raises(ValueError, match=column):
        parse_nhgis_1980_population(source_population_df, Path("1980.csv"))


@pytest.mark.parametrize("suffixes", [("",), ("AA", "AB")])
def test_1980_rejects_rows_without_population_data(suffixes):
    source_population_df = build_1980_population_table(suffixes)
    columns = [
        column for column in source_population_df if column.startswith(("C9D", "C9G"))
    ]
    source_population_df[columns] = None
    with pytest.raises(ValueError):
        parse_nhgis_1980_population(source_population_df, Path("1980.csv"))


def test_1990_csv_loader_retains_et2_mapping_and_computes_poc(tmp_path):
    source_population_df = pd.DataFrame(
        {
            "YEAR": ["Data File Year", "1990"],
            "GISJOIN": ["GIS Join Match Code", "G0100010"],
            "STATEA": ["State Code", "01"],
            "COUNTYA": ["County Code", "001"],
            **{f"ET2{index:03d}": ["Count", str(index)] for index in range(1, 11)},
        }
    )
    source_population_df.to_csv(tmp_path / "nhgis_1990_counties.csv", index=False)

    population_df = load_population_table(1990, tmp_path, "counties")

    assert population_df[["WHITE", "BLACK", "TOTPOP", "POC"]].values.tolist() == [
        [1, 2, 55, 54]
    ]
    assert population_df["JOIN_KEY"].tolist() == ["G0100010"]


def test_nhgis_prefixes_retain_uppercase_ascii_matching_and_deduplication():
    from capy_core.preprocessing.population_tables import indexed_prefixes

    source_population_df = pd.DataFrame(
        columns=["C9D001", "C9DAA001", "C9DAA001", "C9Daa001", "C9DÉ001", "C9DAA002"]
    )

    assert indexed_prefixes(source_population_df, "C9D") == ["C9D", "C9DAA"]


@pytest.mark.parametrize("hispanic_suffixes", [("AA",), ("",)])
def test_1980_rejects_mismatched_geographic_coverage(hispanic_suffixes):
    source_population_df = build_1980_population_table(("AA", "AB"))
    source_population_df = source_population_df.drop(
        columns=[column for column in source_population_df if column.startswith("C9G")]
    )
    for suffix in hispanic_suffixes:
        for index in range(1, 5):
            source_population_df[f"C9G{suffix}{index:03d}"] = "0"
    with pytest.raises(ValueError, match="same geographic breakdowns"):
        parse_nhgis_1980_population(source_population_df, Path("1980.csv"))


@pytest.mark.parametrize("suffixes", [("AA",), ("AB",), ("AC",), ("", "AA", "AB")])
def test_1980_rejects_incomplete_unknown_or_overlapping_layouts(suffixes):
    source_population_df = build_1980_population_table(suffixes)
    with pytest.raises(ValueError, match="without mixing layouts"):
        parse_nhgis_1980_population(source_population_df, Path("1980.csv"))


@pytest.mark.parametrize("index_labels", [[0, 0, 0], [0, 1, 0]])
def test_1980_source_grouping_preserves_rows_with_duplicate_index_labels(index_labels):
    source_population_df = build_1980_population_table(("",), rows=3)
    source_population_df["NHGIS_SOURCE_FILE"] = ["first.csv", "second.csv", "first.csv"]
    source_population_df["C9D001"] = ["10", "20", "30"]
    source_population_df["C9D002"] = ["3", "7", "9"]
    source_population_df["C9G001"] = ["1", "2", "3"]
    source_population_df["C9G002"] = ["0", "1", "2"]
    source_population_df.index = pd.Index(index_labels, name="source_row")
    original_population_df = source_population_df.copy(deep=True)

    population_df = parse_nhgis_1980_population(source_population_df, Path("1980.csv"))

    assert population_df["GISJOIN"].tolist() == ["G0100010", "G0100020", "G0100030"]
    assert population_df["WHITE"].tolist() == [9, 18, 27]
    assert population_df["BLACK"].tolist() == [3, 6, 7]
    assert population_df["TOTPOP"].tolist() == [13, 27, 39]
    pd.testing.assert_index_equal(population_df.index, original_population_df.index)
    pd.testing.assert_frame_equal(source_population_df, original_population_df)
