"""Population definitions, source identities, and end-to-end processing of configured files."""

import csv
import json
from pathlib import Path

import pandas as pd
import pytest
from capy_core.geography_types import GeographyLevel, StudyAreaType
from capy_core.pipeline_config import PipelineConfig, RawDataSubdirectories
from capy_core.process_population.process_tables import process_population_tables
from capy_core.process_population.read_census import read_census_population
from capy_core.process_population.save_tables import (
    PopulationComparison,
    build_population_output_path,
    save_population_parquet,
)
from capy_core.retrieve_data.census.build_requests import (
    BLOCK_GROUP_VARIABLES_2000,
    POPULATION_VARIABLES_BY_YEAR,
)
from capy_core.retrieve_data.raw_file_requests import CensusDataset, CensusFileRequest
from capy_core.retrieve_data.state_codes import STATE_FIPS_CODES


def write_source_table(path, year, geography, geography_rows, *, sf1=False):
    """Write small source records with independently specified, consistent population counts."""
    variables = BLOCK_GROUP_VARIABLES_2000 if sf1 else POPULATION_VARIABLES_BY_YEAR[year]
    counts = [100, 60, 25, 3, 2, 1, 4, 5, 20, 50, 20]
    header = [*variables.split(","), *geography]
    rows = [[parts[0], *map(str, counts), *parts] for parts in geography_rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([header, *rows]))
    return variables


@pytest.mark.parametrize("year,sf1", [(2000, False), (2000, True), (2010, False), (2020, False)])
def test_source_definitions_preserve_ids_and_derive_non_hispanic_counts(tmp_path, year, sf1):
    geography = ["state", "county", "tract", "block group"] if sf1 else ["state", "county", "tract"]
    parts = ["01", "001", "0401" if year == 2000 else "040100"]
    if sf1:
        parts.append("1")
    path = tmp_path / "table.json"
    variables = write_source_table(path, year, geography, [parts], sf1=sf1)
    request = CensusFileRequest(
        destination_relative_path="table.json",
        census_year=year,
        dataset=CensusDataset.SUMMARY_FILE_1 if sf1 else CensusDataset.PL_94_171,
        variables=variables,
        geography_level=GeographyLevel.BLOCK_GROUP if sf1 else GeographyLevel.TRACT,
        state_code="01",
    )
    original = path.read_bytes()

    processed = read_census_population(path, request)
    output = tmp_path / "population.parquet"
    save_population_parquet(processed, output)
    result = pd.read_parquet(output)

    pd.testing.assert_frame_equal(result, processed, check_dtype=False)
    assert result["GEOID"].tolist() == ["01001040100" + ("1" if sf1 else "")]
    assert result["tract"].tolist() == [parts[2]]
    assert result[["TOTPOP", "WHITE", "BLACK", "POC"]].values.tolist() == [[100, 50, 20, 50]]
    assert result["SOURCE_ROW"].tolist() == [1]
    assert result["SOURCE_FILE"].tolist() == ["table.json"]
    for column in [*variables.split(",")[1:], "TOTPOP", "WHITE", "BLACK", "POC"]:
        assert pd.api.types.is_integer_dtype(result[column])
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "state_code,area_name", [("01", "AL"), ("11", "DC"), ("72", "PR"), (None, "national")]
)
def test_population_filenames_identify_state_and_year(state_code, area_name):
    request = CensusFileRequest(
        destination_relative_path="table.json",
        census_year=2020,
        dataset=CensusDataset.PL_94_171,
        variables=POPULATION_VARIABLES_BY_YEAR[2020],
        geography_level=GeographyLevel.STATE if state_code is None else GeographyLevel.TRACT,
        state_code=state_code,
    )

    assert build_population_output_path(
        request.census_year, request.geography_level, request.state_code
    ) == (Path("2020") / request.geography_level.value / f"{area_name}_2020_populations.parquet")


def test_unrepresentable_parquet_count_does_not_replace_existing_file(tmp_path):
    destination = tmp_path / "population.parquet"
    original = pd.DataFrame({"GEOID": ["01001"], "TOTPOP": [100]})
    save_population_parquet(original, destination)
    before = destination.read_bytes()

    with pytest.raises(OverflowError):
        save_population_parquet(pd.DataFrame({"TOTPOP": [2**65]}), destination)

    assert destination.read_bytes() == before
    assert not list(tmp_path.glob(".retrieval-*"))


@pytest.mark.parametrize(
    "problem",
    [
        "duplicate_id",
        "duplicate_column",
        "missing_count",
        "negative_count",
        "race_sum",
        "subset",
        "state",
        "numeric_id",
        "malformed_header",
        "overflow_count",
        "short_tract",
        "five_digit_tract",
    ],
)
def test_invalid_records_fail_without_silently_dropping_or_filling_them(tmp_path, problem):
    path = tmp_path / "table.json"
    variables = write_source_table(
        path, 2000, ["state", "county", "tract"], [["01", "001", "0401"]]
    )
    table = json.loads(path.read_text())
    if problem == "duplicate_id":
        table.append([*table[1][:-1], "040100"])
    elif problem == "duplicate_column":
        table[0][1] = table[0][2]
    elif problem == "missing_count":
        table[1][1] = None
    elif problem == "negative_count":
        table[1][1] = "-1"
    elif problem == "race_sum":
        table[1][1] = "101"
    elif problem == "subset":
        table[1][10] = "61"
    elif problem == "state":
        table[1][-3] = "02"
    elif problem == "malformed_header":
        table[0][1] = ["not a column name"]
    elif problem == "overflow_count":
        table[1][1] = str(2**64)
    elif problem == "short_tract":
        table[1][-1] = "401"
    elif problem == "five_digit_tract":
        table[1][-1] = "04010"
    else:
        table[1][-1] = 401
    path.write_text(json.dumps(table))
    request = CensusFileRequest(
        destination_relative_path="table.json",
        census_year=2000,
        dataset=CensusDataset.PL_94_171,
        variables=variables,
        geography_level=GeographyLevel.TRACT,
        state_code="01",
    )

    with pytest.raises(ValueError):
        read_census_population(path, request)


def prepare_processing_inputs(tmp_path, level=GeographyLevel.TRACT):
    """Populate custom folders with a state partition and both required reference sources."""
    config = PipelineConfig(
        census_geography_years=(2020,),
        census_geography_levels=(GeographyLevel.TRACT,),
        study_area_type=StudyAreaType.MAX_CITY
        if level == GeographyLevel.PLACE
        else StudyAreaType.COUNTY,
        raw_data_directory=Path("inputs"),
        raw_data_subdirectories=RawDataSubdirectories(
            census_population_tables="tables", population_reference_tables="references"
        ),
        processed_population_directory=Path("outputs"),
        file_path_patterns=(f"tables/2020/{level.value}/10/state.json",),
    )
    source = tmp_path / "inputs" / config.file_path_patterns[0]
    geography = (
        ["state", "place"] if level == GeographyLevel.PLACE else ["state", "county", "tract"]
    )
    parts = ["10", "12345"] if level == GeographyLevel.PLACE else ["10", "001", "040100"]
    write_source_table(source, 2020, geography, [parts])
    reference_folder = tmp_path / "inputs/references"
    write_source_table(
        reference_folder / "2020_states.json",
        2020,
        ["state"],
        [[state] for state in STATE_FIPS_CODES],
    )
    with (reference_folder / "census_state_population_totals_2020_release.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Name", "Geography Type", "Year", "Resident Population"])
        writer.writerows((state, "State", "2020", "100") for state in STATE_FIPS_CODES)
    return config, source


def test_configured_processing_preserves_zero_rows_and_rebuilds_deterministically(tmp_path):
    config, source = prepare_processing_inputs(tmp_path)
    table = json.loads(source.read_text())
    table.append(["empty tract", *(["0"] * 11), "10", "001", "040200"])
    source.write_text(json.dumps(table))
    original = source.read_bytes()

    summaries = process_population_tables(config, tmp_path)

    output = tmp_path / "outputs/2020/tracts/DE_2020_populations.parquet"
    population_df = pd.read_parquet(output)
    assert population_df["TOTPOP"].tolist() == [100, 0]
    assert population_df["SOURCE_ROW"].tolist() == [1, 2]
    assert population_df["GEOID"].tolist() == ["10001040100", "10001040200"]
    assert next(item for item in summaries if "tracts" in item.output_file).input_rows == 2
    assert len(summaries) == 2  # Selected tracts plus the required state reference.
    assert all(isinstance(item.comparison, PopulationComparison) for item in summaries)
    national = tmp_path / "outputs/2020/states/national_2020_populations.parquet"
    assert pd.read_parquet(national)["state"].tolist() == list(STATE_FIPS_CODES)
    summary = pd.read_csv(tmp_path / "outputs/processing_summary.csv")
    assert set(summary["comparison"]) == {
        "all_11_counts_match_state",
        "resident_totals_match_published_reference",
    }
    assert set(summary["output_file"]) == {
        "2020/tracts/DE_2020_populations.parquet",
        "2020/states/national_2020_populations.parquet",
    }
    before = {
        path: path.read_bytes() for path in (tmp_path / "outputs").rglob("*") if path.is_file()
    }
    assert process_population_tables(config, tmp_path) == summaries
    assert all(path.read_bytes() == contents for path, contents in before.items())
    assert source.read_bytes() == original


@pytest.mark.parametrize("reference_failure", [False, True])
def test_failed_population_checks_remove_stale_selected_outputs_and_completion_summary(
    tmp_path, reference_failure
):
    config, source = prepare_processing_inputs(tmp_path)
    process_population_tables(config, tmp_path)
    if reference_failure:
        reference = tmp_path / "inputs/references/census_state_population_totals_2020_release.csv"
        reference.write_text(reference.read_text().replace("2020,100", "2020,101"))
    else:
        table = json.loads(source.read_text())
        table[1][1] = "99"
        table[1][2] = "59"  # Internally consistent but no longer matches the state aggregate.
        source.write_text(json.dumps(table))

    with pytest.raises(ValueError):
        process_population_tables(config, tmp_path)
    assert not (tmp_path / "outputs/2020/tracts/DE_2020_populations.parquet").exists()
    assert not (tmp_path / "outputs/processing_summary.csv").exists()
    assert not list((tmp_path / "outputs").rglob(".retrieval-*"))


def test_places_are_not_required_to_partition_a_state(tmp_path):
    config, source = prepare_processing_inputs(tmp_path, GeographyLevel.PLACE)
    table = json.loads(source.read_text())
    table[1][1] = "99"
    table[1][2] = "59"
    source.write_text(json.dumps(table))

    summaries = process_population_tables(config, tmp_path)

    place = next(item for item in summaries if "places" in item.output_file)
    assert place.total_population == 99
    assert place.comparison is PopulationComparison.PLACES_DO_NOT_PARTITION_STATE


@pytest.mark.parametrize("across_rows", [False, True])
def test_population_sums_do_not_wrap_at_machine_integer_limits(tmp_path, across_rows):
    config, source = prepare_processing_inputs(tmp_path)
    header, row = json.loads(source.read_text())
    large_counts = [2**62, 2**62, 2**62, 2**62, 100]
    if across_rows:
        # Each row is internally consistent, but the mathematical state sum is 2**64 + 100.
        rows = [
            ["tract", str(total), str(total), *(["0"] * 9), "10", "001", f"{index:06}"]
            for index, total in enumerate(large_counts, start=1)
        ]
    else:
        row[1:12] = list(map(str, [100, *large_counts, 0, 0, 0, 0, 0]))
        rows = [row]
    source.write_text(json.dumps([header, *rows]))

    with pytest.raises(ValueError, match="expected 100" if across_rows else "Race category"):
        process_population_tables(config, tmp_path)
    assert not (tmp_path / "outputs/2020/tracts/DE_2020_populations.parquet").exists()


def test_processed_folder_cannot_replace_raw_inputs(tmp_path):
    config, source = prepare_processing_inputs(tmp_path)
    config.processed_population_directory = config.raw_data_directory
    original = source.read_bytes()
    with pytest.raises(ValueError, match="must be separate"):
        process_population_tables(config, tmp_path)
    assert source.read_bytes() == original


def test_historical_references_load_once_before_out_of_order_archives(tmp_path, monkeypatch):
    from capy_core.process_population import process_tables
    from capy_core.process_population.nhgis_columns import NHGIS_COUNT_COLUMNS
    from capy_core.retrieve_data.nhgis.build_requests import build_historical_population_requests
    from capy_core.retrieve_data.nhgis.identifiers import NhgisGeographyLevel
    from capy_core.retrieve_data.raw_file_requests import GeographyRequest

    requests = build_historical_population_requests(
        RawDataSubdirectories(),
        (GeographyRequest(census_year=1980, geography_level=GeographyLevel.COUNTY),),
    )
    # The county archive precedes the state reference in filename order.
    requests.sort(key=lambda request: request.destination_relative_path)
    state_codes = [state_code for state_code in STATE_FIPS_CODES if state_code != "72"]
    states_df = pd.DataFrame({"state": state_codes})
    for column in [*NHGIS_COUNT_COLUMNS[1980], "TOTPOP", "WHITE", "BLACK", "POC"]:
        states_df[column] = 0

    operations = []

    def read_archive(path, request):
        if request.geographic_levels == (NhgisGeographyLevel.STATE,):
            operations.append("read state reference")
            yield states_df
        else:
            assert operations == ["read state reference", "compare published totals"]
            operations.append("read counties")
            for state_code in state_codes:
                yield states_df.loc[states_df["state"].eq(state_code)]

    def compare_published_totals(population_df, reference_directory, census_year):
        assert population_df is states_df
        assert reference_directory == tmp_path / "references"
        operations.append("compare published totals")

    monkeypatch.setattr(process_tables, "read_nhgis_population_by_state", read_archive)
    monkeypatch.setattr(
        process_tables, "check_historical_published_totals", compare_published_totals
    )

    summaries = process_tables.process_historical_population_tables(
        requests, tmp_path / "raw", tmp_path / "processed", tmp_path / "references"
    )

    assert operations == ["read state reference", "compare published totals", "read counties"]
    assert len(summaries) == 52
    saved_states_df = pd.read_parquet(
        tmp_path / "processed/1980/states/national_1980_populations.parquet"
    )
    pd.testing.assert_frame_equal(saved_states_df, states_df)


def test_partial_parquet_write_does_not_replace_existing_output(tmp_path, monkeypatch):
    destination = tmp_path / "population.parquet"
    original_df = pd.DataFrame({"GEOID": ["01001"], "TOTPOP": [100]})
    save_population_parquet(original_df, destination)
    original_bytes = destination.read_bytes()

    def fail_after_writing(population_df, temporary_path, **kwargs):
        temporary_path.write_bytes(b"partial parquet")
        raise OSError("write interrupted")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail_after_writing)
    with pytest.raises(OSError, match="write interrupted"):
        save_population_parquet(original_df, destination)

    assert destination.read_bytes() == original_bytes
    assert not list(tmp_path.glob(".retrieval-*"))


@pytest.mark.parametrize("invalid", [False, True])
def test_census_count_conversion_leaves_source_unchanged(invalid):
    from capy_core.process_population.read_census import convert_and_check_census_population_counts
    from capy_core.retrieve_data.census.table_columns import CENSUS_POPULATION_COLUMNS

    columns = CENSUS_POPULATION_COLUMNS[2020, CensusDataset.PL_94_171]
    counts = {column: "0" for column in columns.count_columns}
    counts.update({columns.total: "10", columns.white_alone: "10", columns.non_hispanic_white: "8"})
    if invalid:
        counts[columns.white_alone] = "invalid"

    population_df = pd.DataFrame([counts], index=[7])
    population_df["source_label"] = "unchanged"
    original_df = population_df.copy()

    if invalid:
        with pytest.raises(ValueError, match="nonnegative integer"):
            convert_and_check_census_population_counts(population_df, columns)
    else:
        counts_df = convert_and_check_census_population_counts(population_df, columns)
        assert counts_df.index.tolist() == [7]
        assert list(counts_df.columns) == list(columns.count_columns)
        assert counts_df[columns.total].iloc[0] == 10
        assert counts_df[columns.non_hispanic_white].iloc[0] == 8

    pd.testing.assert_frame_equal(population_df, original_df)


@pytest.mark.parametrize("invalid", [False, True])
def test_1980_derivation_returns_counts_without_changing_source(invalid):
    from capy_core.process_population.nhgis_columns import NHGIS_COUNT_COLUMNS, Nhgis1980Column
    from capy_core.process_population.read_nhgis import derive_1980_population_counts

    counts = dict.fromkeys(NHGIS_COUNT_COLUMNS[1980], 0)
    counts.update(
        {
            Nhgis1980Column.TOTAL: 10,
            Nhgis1980Column.WHITE: 8,
            Nhgis1980Column.BLACK: 2,
            Nhgis1980Column.HISPANIC_TOTAL: 2,
            Nhgis1980Column.HISPANIC_WHITE: 2,
        }
    )
    if invalid:
        counts[Nhgis1980Column.HISPANIC_WHITE] = 3

    population_df = pd.DataFrame([counts], index=[7], dtype=object)
    original_df = population_df.copy()

    if invalid:
        with pytest.raises(ValueError, match="Hispanic race counts"):
            derive_1980_population_counts(population_df)
    else:
        counts_df = derive_1980_population_counts(population_df)
        expected_df = pd.DataFrame(
            {"TOTPOP": [10], "WHITE": [6], "BLACK": [2]}, index=[7], dtype=object
        )
        pd.testing.assert_frame_equal(counts_df, expected_df)

    pd.testing.assert_frame_equal(population_df, original_df)
