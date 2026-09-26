"""Small NHGIS source archives with independently specified population expectations."""

import csv
from contextlib import closing
from io import StringIO
from zipfile import ZipFile

import pytest
from capy_core.process_population.read_nhgis import read_nhgis_population_by_state
from capy_core.retrieve_data.nhgis.identifiers import NhgisDataset, NhgisGeographyLevel
from capy_core.retrieve_data.raw_file_requests import NhgisTableFileRequest


def write_historical_archive(tmp_path, census_year, *, replacements=None, extra_cell=False):
    """Write one county with race and Hispanic-origin counts in the original source layout."""
    population_row = {
        "GISJOIN": "G0100010",
        "YEAR": str(census_year),
        "STATEA": "01",
        "COUNTYA": "001",
    }

    if census_year == 1980:
        population_row.update({f"C9D{number:03d}": "0" for number in range(1, 16)})
        population_row.update(
            C7L001="110",
            C9D001="70",
            C9D002="25",
            C9D003="5",
            C9D015="10",
            C9F001="20",
            C9G001="10",
            C9G002="3",
            C9G003="2",
            C9G004="5",
        )
        dataset = NhgisDataset.STF1_1980
        tables = ("NT1A", "NT7", "NT9A", "NT9B")
        dataset_code = "ds104"
    else:
        population_row.update(
            ET1001="110",
            ET2001="60",
            ET2002="22",
            ET2003="3",
            ET2004="2",
            ET2005="3",
            ET2006="10",
            ET2007="3",
            ET2008="2",
            ET2009="1",
            ET2010="4",
        )
        dataset = NhgisDataset.STF1_1990
        tables = ("NP1", "NP10")
        dataset_code = "ds120"

    population_row.update(replacements or {})
    description_row = dict.fromkeys(population_row, "unused")
    description_row["GISJOIN"] = "GIS Join Match Code"
    description_row["YEAR"] = "Data File Year"
    data_row = list(population_row.values())

    if extra_cell:
        data_row.insert(0, "unexpected")

    csv_text = StringIO()
    writer = csv.writer(csv_text)
    writer.writerow(population_row)
    writer.writerow(description_row.values())
    writer.writerow(data_row)
    csv_member = f"nhgis_test_{dataset_code}_{census_year}_county.csv"
    archive_path = tmp_path / "population.zip"

    with ZipFile(archive_path, "w") as archive:
        archive.writestr(csv_member, csv_text.getvalue())

    request = NhgisTableFileRequest(
        destination_relative_path="population.zip",
        dataset_name=dataset,
        tables=tables,
        geographic_levels=(NhgisGeographyLevel.COUNTY,),
    )

    return archive_path, request, csv_member


@pytest.mark.parametrize("census_year", [1980, 1990])
def test_historical_source_counts_and_identifiers_survive_parsing(tmp_path, census_year):
    archive_path, request, csv_member = write_historical_archive(tmp_path, census_year)
    original_bytes = archive_path.read_bytes()

    with closing(read_nhgis_population_by_state(archive_path, request)) as population_tables:
        (population_df,) = population_tables

    assert population_df[["TOTPOP", "WHITE", "BLACK", "POC"]].values.tolist() == [[110, 60, 22, 50]]
    assert population_df[["GEOID", "state", "COUNTYA"]].values.tolist() == [
        ["G0100010", "01", "001"]
    ]
    assert population_df["SOURCE_ROW"].tolist() == [1]
    assert population_df["SOURCE_MEMBER"].tolist() == [csv_member]
    assert archive_path.read_bytes() == original_bytes


@pytest.mark.parametrize("census_year", [1980, 1990])
@pytest.mark.parametrize("bad_count", ["", "-1", "1.5"])
def test_historical_reader_rejects_invalid_counts(tmp_path, census_year, bad_count):
    count_column = "C7L001" if census_year == 1980 else "ET1001"
    archive_path, request, _ = write_historical_archive(
        tmp_path, census_year, replacements={count_column: bad_count}
    )

    with (
        closing(read_nhgis_population_by_state(archive_path, request)) as population_tables,
        pytest.raises(ValueError, match="nonnegative integer counts"),
    ):
        list(population_tables)


@pytest.mark.parametrize("census_year", [1980, 1990])
@pytest.mark.parametrize(
    "replacements,error_message",
    [
        ({"YEAR": "2020"}, "outside"),
        ({"GISJOIN": ""}, "no GISJOIN"),
        ({"COUNTYA": ""}, "county codes"),
    ],
)
def test_historical_reader_rejects_wrong_year_or_missing_identity(
    tmp_path, census_year, replacements, error_message
):
    archive_path, request, _ = write_historical_archive(
        tmp_path, census_year, replacements=replacements
    )

    with (
        closing(read_nhgis_population_by_state(archive_path, request)) as population_tables,
        pytest.raises(ValueError, match=error_message),
    ):
        list(population_tables)


@pytest.mark.parametrize("census_year", [1980, 1990])
def test_historical_reader_rejects_inconsistent_population_totals(tmp_path, census_year):
    count_column = "C7L001" if census_year == 1980 else "ET1001"
    archive_path, request, _ = write_historical_archive(
        tmp_path, census_year, replacements={count_column: "111"}
    )

    with (
        closing(read_nhgis_population_by_state(archive_path, request)) as population_tables,
        pytest.raises(ValueError, match="sum to total"),
    ):
        list(population_tables)


def test_historical_reader_rejects_extra_csv_cell_instead_of_inferred_index(tmp_path):
    archive_path, request, _ = write_historical_archive(tmp_path, 1990, extra_cell=True)

    with (
        closing(read_nhgis_population_by_state(archive_path, request)) as population_tables,
        pytest.raises(ValueError, match="more fields than its header"),
    ):
        list(population_tables)


def test_missing_historical_state_reference_names_year_and_archive(tmp_path):
    from capy_core.process_population.process_tables import process_historical_population_tables

    _, request, _ = write_historical_archive(tmp_path, 1980)

    with pytest.raises(ValueError, match="population.zip: Missing 1980 NHGIS state-reference"):
        process_historical_population_tables([request], tmp_path, tmp_path / "output", tmp_path)

    assert not (tmp_path / "output").exists()
