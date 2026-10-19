"""Workbook comparisons that detect source-category errors hidden by study-group totals."""

import pandas as pd
import pytest
import us
from national_pipeline.process_population.check_nhgis_totals import (
    check_historical_published_totals,
)
from national_pipeline.retrieve_data.state_codes import STATE_FIPS_CODES


def write_state_references(tmp_path, census_year):
    """Write independent source counts and published workbooks with the Census header layout."""
    state_codes = [code for code in STATE_FIPS_CODES if code != "72"]
    state_names = us.states.mapping("fips", "name")
    source_counts = {"TOTPOP": 110, "WHITE": 60, "BLACK": 22, "POC": 50}
    e_table_df = pd.DataFrame("", index=range(57), columns=range(19))
    e_table_df.iat[0, 0] = f"Table E: {census_year} (100-Percent Data)"
    race_headings = {4: "White", 7: "Black"}

    if census_year == 1980:
        source_counts.update({f"C9D{number:03d}": 0 for number in range(1, 16)})
        source_counts.update(
            C7L001=110,
            C9D001=70,
            C9D002=25,
            C9D003=1,
            C9D004=2,
            C9D005=3,
            C9D006=2,
            C9D007=3,
            C9D015=4,
            C9F001=20,
            C9G001=10,
            C9G002=3,
            C9G003=3,
            C9G004=4,
        )
        e_counts = [110, 20, 90, 70, 10, 60, 25, 3, 22, 15, 7, 8]
        e_filename = "census_working_paper_56_1980_tableE-03.xlsx"
    else:
        source_counts.update(
            ET1001=110,
            ET2001=60,
            ET2002=22,
            ET2003=3,
            ET2004=2,
            ET2005=3,
            ET2006=10,
            ET2007=3,
            ET2008=2,
            ET2009=1,
            ET2010=4,
        )
        e_counts = [110, 20, 90, 70, 10, 60, 25, 3, 22, 5, 2, 3, 3, 1, 2, 7, 4, 3]
        e_filename = "census_working_paper_56_1990_tableE-01.xlsx"
        race_headings.update(
            {
                10: "American Indian, Eskimo, and Aleut",
                13: "Asian and Pacific Islander",
                16: "Other race",
            }
        )

    for column, heading in race_headings.items():
        e_table_df.iat[3, column] = heading
        e_table_df.iloc[4, column : column + 3] = [
            "Total",
            "Hispanic\n origin",
            "Not of Hispanic origin",
        ]

    source_rows = []

    for row_number, state_code in enumerate(state_codes, start=6):
        multiplier = int(state_code)
        e_table_df.iat[row_number, 0] = f".{state_names[state_code]}"
        e_table_df.iloc[row_number, 1 : len(e_counts) + 1] = [
            str(count * multiplier) for count in e_counts
        ]
        source_rows.append(
            {
                "state": state_code,
                **{column: count * multiplier for column, count in source_counts.items()},
            }
        )

    e_table_df.to_excel(tmp_path / e_filename, header=False, index=False)

    if census_year == 1980:
        a_table_df = pd.DataFrame("", index=range(57), columns=range(14))
        a_table_df.iat[0, 0] = "Table A-3: 1980 (100-Percent Data)"
        a_table_df.iat[2, 13] = "Spanish\norigin\n(of any race)"

        for column, heading in {
            3: "White",
            5: "Black",
            7: "American Indian,\nEskimo,\nand Aleut",
            9: "Asian and\nPacific Islander",
            11: "Other race",
        }.items():
            a_table_df.iat[4, column] = heading

        for column in (3, 5, 7, 9, 11, 13):
            a_table_df.iat[5, column] = "Number"

        for row_number, state_code in enumerate(state_codes, start=6):
            a_table_df.iat[row_number, 0] = state_names[state_code]

            for column, count in {3: 70, 5: 25, 7: 6, 9: 5, 11: 4, 13: 20}.items():
                a_table_df.iat[row_number, column] = str(count * int(state_code))

        a_table_df.to_excel(
            tmp_path / "census_working_paper_56_1980_tableA-03.xlsx", header=False, index=False
        )

    return pd.DataFrame(source_rows[::-1])


@pytest.mark.parametrize("census_year", [1980, 1990])
def test_workbooks_match_counts_by_state_without_changing_inputs(tmp_path, census_year):
    states_df = write_state_references(tmp_path, census_year)
    original_df = states_df.copy(deep=True)

    check_historical_published_totals(states_df, tmp_path, census_year)

    pd.testing.assert_frame_equal(states_df, original_df)


@pytest.mark.parametrize(
    "census_year,increased_column,decreased_column,workbook",
    [
        (1980, "C9D003", "C9D006", "tableA-03"),
        (1990, "ET2003", "ET2004", "tableE-01"),
        (1990, "ET2008", "ET2009", "tableE-01"),
    ],
)
def test_race_category_shift_fails_even_when_study_counts_stay_the_same(
    tmp_path, census_year, increased_column, decreased_column, workbook
):
    states_df = write_state_references(tmp_path, census_year)
    original_study_df = states_df[["TOTPOP", "WHITE", "BLACK", "POC"]].copy()
    states_df.loc[0, increased_column] += 1
    states_df.loc[0, decreased_column] -= 1

    with pytest.raises(ValueError, match=f"{workbook}.*differs from published totals"):
        check_historical_published_totals(states_df, tmp_path, census_year)

    pd.testing.assert_frame_equal(states_df[original_study_df.columns], original_study_df)


@pytest.mark.parametrize("damaged_part", ["heading", "state", "year"])
def test_workbook_layout_or_coverage_changes_are_rejected(tmp_path, damaged_part):
    states_df = write_state_references(tmp_path, 1990)
    workbook_path = tmp_path / "census_working_paper_56_1990_tableE-01.xlsx"
    published_df = pd.read_excel(workbook_path, header=None, dtype=str).fillna("")

    if damaged_part == "heading":
        published_df.iat[3, 10] = "Other race"
    elif damaged_part == "state":
        published_df.iat[6, 0] = published_df.iat[7, 0]
    else:
        published_df.iat[0, 0] = "1980 (100-Percent Data)"

    published_df.to_excel(workbook_path, header=False, index=False)

    with pytest.raises(ValueError, match="Expected heading|each state once|wrong year"):
        check_historical_published_totals(states_df, tmp_path, 1990)
