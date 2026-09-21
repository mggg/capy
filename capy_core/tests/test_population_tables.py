from pathlib import Path

import pandas as pd
import pytest

from capy_core.preprocessing.population_tables import (
    load_population_table,
    parse_nhgis_1980_population,
    parse_population_counts,
)


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


def test_1980_concatenated_tables_distinguish_absent_prefixes_from_missing_cells():
    source_population_dfs = []
    for suffix, source_file in (
        ("AA", "urban.csv"),
        ("AB", "rural.csv"),
        ("", "total.csv"),
    ):
        source_population_dfs.append(
            pd.DataFrame(
                {
                    "NHGIS_SOURCE_FILE": [source_file, source_file],
                    "GISJOIN": [f"G{suffix}1", f"G{suffix}2"],
                    "STATEA": ["01", "01"],
                    "COUNTYA": ["001", "001"],
                    f"C9D{suffix}001": ["10", "20"],
                    f"C9D{suffix}002": ["3", "7"],
                    f"C9D{suffix}003": ["1", "2"],
                    f"C9G{suffix}001": ["1", "2"],
                    f"C9G{suffix}002": ["0", "1"],
                }
            )
        )
    for index in range(4, 16):
        source_population_dfs[-1][f"C9D{index:03d}"] = "0"
    source_population_df = pd.concat(source_population_dfs, ignore_index=True)
    source = Path("nhgis_1980.csv")

    population_df = parse_nhgis_1980_population(source_population_df, source)

    assert population_df["WHITE"].tolist() == [9, 18, 9, 18, 9, 18]
    assert population_df["BLACK"].tolist() == [3, 6, 3, 6, 3, 6]
    assert population_df["TOTPOP"].tolist() == [14, 29, 14, 29, 14, 29]
    source_population_df.loc[0, "C9DAA003"] = None
    with pytest.raises(ValueError, match="urban.csv: C9DAA003"):
        parse_nhgis_1980_population(source_population_df, source)


def test_1980_requires_full_unsplit_race_table_and_nonnegative_subtraction():
    source_population_df = pd.DataFrame(
        {
            "GISJOIN": ["G0100010"],
            "STATEA": ["01"],
            "COUNTYA": ["001"],
            **{f"C9D{index:03d}": ["1"] for index in range(1, 16)},
            "C9G001": ["2"],
            "C9G002": ["0"],
        }
    )
    with pytest.raises(ValueError, match="WHITE"):
        parse_nhgis_1980_population(source_population_df, Path("1980.csv"))
    with pytest.raises(ValueError, match="C9D015"):
        parse_nhgis_1980_population(
            source_population_df.drop(columns="C9D015"), Path("1980.csv")
        )
    with pytest.raises(ValueError, match="C9G001"):
        parse_nhgis_1980_population(
            source_population_df.drop(columns="C9G001"), Path("1980.csv")
        )


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


@pytest.mark.parametrize("hispanic_prefixes", [("C9GAA", "C9GAB"), ("C9G",)])
def test_1980_discovers_hispanic_prefixes_independently(hispanic_prefixes):
    source_population_df = pd.DataFrame(
        {
            "GISJOIN": ["G0100010"],
            "STATEA": ["01"],
            "COUNTYA": ["001"],
            "C9DAA001": ["30"],
            "C9DAA002": ["10"],
            "C9DAA003": ["3"],
        }
    )
    for prefix in hispanic_prefixes:
        source_population_df[f"{prefix}001"] = "2"
        source_population_df[f"{prefix}002"] = "1"

    population_df = parse_nhgis_1980_population(source_population_df, Path("1980.csv"))

    assert population_df["WHITE"].tolist() == [30 - 2 * len(hispanic_prefixes)]
    assert population_df["BLACK"].tolist() == [10 - len(hispanic_prefixes)]
    assert population_df["TOTPOP"].tolist() == [43]


@pytest.mark.parametrize("index_labels", [[0, 0, 0], [0, 1, 0]])
def test_1980_source_grouping_preserves_rows_with_duplicate_index_labels(index_labels):
    source_population_df = pd.DataFrame(
        {
            "GISJOIN": ["G0100010", "G0100030", "G0100050"],
            "STATEA": ["01"] * 3,
            "COUNTYA": ["001", "003", "005"],
            "NHGIS_SOURCE_FILE": ["urban.csv", "rural.csv", "urban.csv"],
            "C9DAA001": ["10", "20", "30"],
            "C9DAA002": ["3", "7", "9"],
            "C9GAA001": ["1", "2", "3"],
            "C9GAA002": ["0", "1", "2"],
        },
        index=pd.Index(index_labels, name="source_row"),
    )
    original_population_df = source_population_df.copy(deep=True)

    population_df = parse_nhgis_1980_population(source_population_df, Path("1980.csv"))

    assert population_df["GISJOIN"].tolist() == ["G0100010", "G0100030", "G0100050"]
    assert population_df["WHITE"].tolist() == [9, 18, 27]
    assert population_df["BLACK"].tolist() == [3, 6, 7]
    assert population_df["TOTPOP"].tolist() == [13, 27, 39]
    pd.testing.assert_index_equal(population_df.index, original_population_df.index)
    pd.testing.assert_frame_equal(source_population_df, original_population_df)
