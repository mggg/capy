"""Process selected Census and NHGIS population files and save their population accounting."""

from contextlib import closing
from pathlib import Path
from typing import Literal
from zipfile import BadZipFile

import pandas as pd
from tqdm import tqdm

from national_pipeline.data_directories import resolve_separate_output_directory
from national_pipeline.derived_file_paths import build_population_output_path
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import PipelineConfig, RawDataSubdirectories
from national_pipeline.population_table_columns import GeographyColumn
from national_pipeline.retrieve_data.census.build_published_file_requests import (
    CENSUS_RESIDENT_TOTALS_FILENAME,
)
from national_pipeline.retrieve_data.census.build_requests import (
    build_census_state_reference_request,
)
from national_pipeline.retrieve_data.nhgis.build_requests import (
    build_historical_population_requests,
)
from national_pipeline.retrieve_data.nhgis.identifiers import NhgisGeographyLevel
from national_pipeline.retrieve_data.prepare_file_requests import (
    select_raw_file_requests,
)
from national_pipeline.retrieve_data.raw_file_requests import (
    CensusFileRequest,
    GeographyRequest,
    NhgisTableFileRequest,
    RawFileRequest,
)
from national_pipeline.retrieve_data.state_codes import STATE_FIPS_CODES

from .check_nhgis_totals import check_historical_published_totals, check_nhgis_state_sum
from .check_totals import check_population_state_sum, check_published_state_totals
from .read_census import read_census_population
from .read_nhgis import (
    NHGIS_POPULATION_LEVELS,
    describe_nhgis_population_request,
    read_nhgis_population_by_state,
)
from .save_tables import (
    PopulationComparison,
    PopulationTableSummary,
    build_population_output_paths,
    save_population_parquet,
    save_population_summary,
    summarize_population_table,
)


def process_population_tables(
    config: PipelineConfig, repository_root: Path
) -> list[PopulationTableSummary]:
    """Process population inputs using the configured folders and raw-file selections.

    Required state tables and published resident totals are read even if filename filters omit
    them. Historical tables use their corresponding NHGIS states and published workbooks.
    Diagnostic extracts remain join-stage inputs.

    Reruns remove selected derived files and the previous summary before checking inputs, so a
    failed run cannot leave an old selected output looking current. Files from other selections
    remain. A successful run writes processing_summary.csv listing exactly this run's outputs.

    Args:
        config (PipelineConfig): Input selections and raw/processed population folders.
        repository_root (Path): Base for relative configured paths.

    Returns:
        list[PopulationTableSummary]: Row counts, population totals, and checks for saved tables.

    Raises:
        OSError: A required input cannot be read or an output cannot be written.
        ValueError: Inputs, selections, output locations, or population checks are invalid.
    """
    selected_requests = select_raw_file_requests(config)
    census_requests, nhgis_requests = select_population_requests(
        selected_requests, config.raw_data_subdirectories
    )
    raw_data_directory = (repository_root / config.raw_data_directory).resolve()
    population_table_directory = resolve_separate_output_directory(
        repository_root, config.processed_population_directory, (raw_data_directory,)
    )

    remove_selected_population_outputs(census_requests, nhgis_requests, population_table_directory)

    population_reference_directory = (
        raw_data_directory / config.raw_data_subdirectories.population_reference_tables
    )

    summaries = process_census_population_tables(
        census_requests,
        raw_data_directory,
        population_table_directory,
        population_reference_directory,
    )

    summaries.extend(
        process_historical_population_tables(
            nhgis_requests,
            raw_data_directory,
            population_table_directory,
            population_reference_directory,
        )
    )

    save_population_summary(summaries, population_table_directory / "processing_summary.csv")

    return summaries


def remove_selected_population_outputs(
    census_requests: list[CensusFileRequest],
    nhgis_requests: list[NhgisTableFileRequest],
    population_table_directory: Path,
) -> None:
    """Remove selected derived tables and the summary so stale results cannot survive a rerun.

    Historical archives cover the 50 states and DC; their expected output names are known before
    reading. Validate every destination before removing any file. Other selections remain intact.

    Args:
        census_requests (list[CensusFileRequest]): Selected modern inputs and state references.
        nhgis_requests (list[NhgisTableFileRequest]): Selected historical population archives.
        population_table_directory (Path): Resolved root for processed files, separate from
            raw inputs.

    Raises:
        ValueError: An output resolves outside the configured folder.
        OSError: A selected file cannot be removed.
    """
    summary_path = population_table_directory / "processing_summary.csv"
    population_paths_by_year_and_level = build_population_output_paths(
        census_requests, nhgis_requests
    )
    output_paths = [
        population_table_directory / relative_path
        for state_paths in population_paths_by_year_and_level.values()
        for relative_path in state_paths.values()
    ]

    for output_path in [summary_path, *output_paths]:
        if not output_path.resolve().is_relative_to(population_table_directory):
            raise ValueError(
                f"Processed output resolves outside its configured folder: {output_path}"
            )

    for output_path in [summary_path, *output_paths]:
        output_path.unlink(missing_ok=True)


def process_census_population_tables(
    census_requests: list[CensusFileRequest],
    raw_data_directory: Path,
    population_table_directory: Path,
    population_reference_directory: Path,
) -> list[PopulationTableSummary]:
    """Check modern state references, then process each selected Census PL/SF1 table.

    Args:
        census_requests (list[CensusFileRequest]): Selected population inputs and state references.
        raw_data_directory (Path): Configured raw-data root.
        population_table_directory (Path): Separate derived-population root.
        population_reference_directory (Path): Folder containing the published
            resident-population CSV.

    Returns:
        list[PopulationTableSummary]: Accounting for each saved national/state Parquet table.

    Raises:
        OSError: An input or published reference cannot be read.
        ValueError: Population checks or writing a table fails; errors identify its input.
    """
    state_requests = [
        request for request in census_requests if request.geography_level == GeographyLevel.STATE
    ]
    published_totals_csv_path = population_reference_directory / CENSUS_RESIDENT_TOTALS_FILENAME
    state_tables_by_year = load_census_state_references(
        raw_data_directory, published_totals_csv_path, state_requests
    )

    summaries = []

    for request in tqdm(census_requests, desc="Population tables", unit="table", disable=None):
        try:
            if request.geography_level == GeographyLevel.STATE:
                population_df = state_tables_by_year[request.census_year]
                comparison = PopulationComparison.RESIDENT_TOTALS_MATCH_PUBLISHED
            else:
                population_df = read_census_population(
                    raw_data_directory / request.destination_relative_path, request
                )

                comparison = check_population_state_sum(
                    population_df, request, state_tables_by_year[request.census_year]
                )

            output_path = build_population_output_path(
                request.census_year, request.geography_level, request.state_code
            )
            save_population_parquet(population_df, population_table_directory / output_path)

        except (OSError, ValueError, OverflowError, BadZipFile) as error:
            raise ValueError(f"{request.destination_relative_path}: {error}") from error

        summaries.append(
            summarize_population_table(
                population_df, request.destination_relative_path, output_path, comparison
            )
        )

    return summaries


def select_population_requests(
    selected_requests: list[RawFileRequest],
    directories: RawDataSubdirectories,
) -> tuple[list[CensusFileRequest], list[NhgisTableFileRequest]]:
    """Select Census and NHGIS populations, adding the state references needed for checks.

    Args:
        selected_requests (list[RawFileRequest]): Raw inputs already selected for this run.
        directories (RawDataSubdirectories): Folders used to locate required state references.

    Returns:
        tuple[list[CensusFileRequest], list[NhgisTableFileRequest]]: Modern and historical inputs,
            each including the needed state references once.

    Raises:
        ValueError: Selections contain no population tables or use unsupported NHGIS datasets.
    """
    census_requests = [
        request for request in selected_requests if isinstance(request, CensusFileRequest)
    ]
    nhgis_requests = [
        request
        for request in selected_requests
        if isinstance(request, NhgisTableFileRequest)
        and len(request.geographic_levels) == 1
        and request.geographic_levels[0] in NHGIS_POPULATION_LEVELS
    ]

    if not census_requests and not nhgis_requests:
        raise ValueError("Select at least one Census or NHGIS population table for processing")

    census_years: set[Literal[2000, 2010, 2020]] = {
        request.census_year for request in census_requests
    }

    for census_year in sorted(census_years):
        reference_request = build_census_state_reference_request(directories, census_year)

        if reference_request not in census_requests:
            census_requests.append(reference_request)

    historical_years = {describe_nhgis_population_request(request)[0] for request in nhgis_requests}
    reference_selections = tuple(
        GeographyRequest(census_year=year, geography_level=GeographyLevel.STATE)
        for year in (1980, 1990)
        if year in historical_years
    )

    for reference_request in build_historical_population_requests(
        directories, reference_selections
    ):
        if reference_request not in nhgis_requests:
            nhgis_requests.append(reference_request)

    census_requests.sort(key=lambda request: request.destination_relative_path)
    # Keep national state tables first in the output summary.
    nhgis_requests.sort(
        key=lambda request: (
            request.geographic_levels != (NhgisGeographyLevel.STATE,),
            request.destination_relative_path,
        )
    )

    return census_requests, nhgis_requests


def load_census_state_references(
    raw_data_directory: Path,
    published_totals_csv_path: Path,
    state_requests: list[CensusFileRequest],
) -> dict[int, pd.DataFrame]:
    """Read the small state tables and compare them with published resident population totals.

    Args:
        raw_data_directory (Path): Resolved raw-data root.
        published_totals_csv_path (Path): Published resident totals used to check every state.
        state_requests (list[CensusFileRequest]): One national state table per needed Census year.

    Returns:
        dict[int, pd.DataFrame]: Validated state tables keyed by Census year.

    Raises:
        OSError: A reference file is missing or unreadable.
        ValueError: A reference fails its structure, count, coverage, or total checks.
    """
    state_tables_by_year = {}

    for request in state_requests:
        states_df = read_census_population(
            raw_data_directory / request.destination_relative_path, request
        )

        check_published_state_totals(states_df, published_totals_csv_path, request.census_year)

        state_tables_by_year[request.census_year] = states_df

    return state_tables_by_year


def process_historical_population_tables(
    nhgis_requests: list[NhgisTableFileRequest],
    raw_data_directory: Path,
    population_table_directory: Path,
    population_reference_directory: Path,
) -> list[PopulationTableSummary]:
    """Load and check NHGIS state references, then process each selected historical level.

    Args:
        nhgis_requests (list[NhgisTableFileRequest]): Population extracts and their state references.
        raw_data_directory (Path): Configured raw-data root.
        population_table_directory (Path): Separate derived-population root.
        population_reference_directory (Path): Configured folder for Census Working Paper 56
            workbooks.

    Returns:
        list[PopulationTableSummary]: Accounting for each saved national/state Parquet table.

    Raises:
        ValueError: An archive cannot be read, checked, or saved, or its year lacks a
            state-reference request. The error names the input archive.
    """
    state_requests = [
        request
        for request in nhgis_requests
        if request.geographic_levels == (NhgisGeographyLevel.STATE,)
    ]
    state_tables_by_year = load_nhgis_state_references(
        state_requests, raw_data_directory, population_reference_directory
    )

    summaries = []

    for request in tqdm(
        nhgis_requests, desc="NHGIS population archives", unit="archive", disable=None
    ):
        try:
            census_year, geography_level = describe_nhgis_population_request(request)

            if census_year not in state_tables_by_year:
                raise ValueError(f"Missing {census_year} NHGIS state-reference request")

            states_df = state_tables_by_year[census_year]

            if geography_level == GeographyLevel.STATE:
                output_path = build_population_output_path(census_year, geography_level)
                save_population_parquet(states_df, population_table_directory / output_path)

                summaries.append(
                    summarize_population_table(
                        states_df,
                        request.destination_relative_path,
                        output_path,
                        PopulationComparison.STUDY_COUNTS_MATCH_PUBLISHED,
                    )
                )

            else:
                summaries.extend(
                    process_historical_substate_archive(
                        request, raw_data_directory, population_table_directory, states_df
                    )
                )

        except (OSError, ValueError, OverflowError, BadZipFile) as error:
            raise ValueError(f"{request.destination_relative_path}: {error}") from error

    return summaries


def load_nhgis_state_references(
    state_requests: list[NhgisTableFileRequest],
    raw_data_directory: Path,
    population_reference_directory: Path,
) -> dict[int, pd.DataFrame]:
    """Read NHGIS state tables and compare study and source counts with published workbooks.

    Args:
        state_requests (list[NhgisTableFileRequest]): One national state extract per required year.
        raw_data_directory (Path): Configured raw-data root containing the archives.
        population_reference_directory (Path): Folder containing Census Working Paper 56 workbooks.

    Returns:
        dict[int, pd.DataFrame]: State tables by Census year, after population and coverage checks.

    Raises:
        ValueError: An archive or reference cannot be read or fails its checks. The error names
            the state archive; filesystem errors also identify the unreadable file.
    """
    state_tables_by_year = {}

    for request in state_requests:
        try:
            census_year, _ = describe_nhgis_population_request(request)

            with closing(
                read_nhgis_population_by_state(
                    raw_data_directory / request.destination_relative_path, request
                )
            ) as population_tables:
                (states_df,) = population_tables

            check_historical_published_totals(
                states_df, population_reference_directory, census_year
            )

            state_tables_by_year[census_year] = states_df

        except (OSError, ValueError, OverflowError, BadZipFile) as error:
            raise ValueError(f"{request.destination_relative_path}: {error}") from error

    return state_tables_by_year


def process_historical_substate_archive(
    request: NhgisTableFileRequest,
    raw_data_directory: Path,
    population_table_directory: Path,
    states_df: pd.DataFrame,
) -> list[PopulationTableSummary]:
    """Compare one substate NHGIS archive with its state reference and save each state's units.

    Reading finishes with a check that all 50 states and DC appeared. If any step fails, the
    archive reader closes; tables already saved remain until the next run removes selected outputs.

    Args:
        request (NhgisTableFileRequest): One national population archive below state level.
        raw_data_directory (Path): Folder containing the downloaded archive.
        population_table_directory (Path): Separate folder for processed population tables.
        states_df (pd.DataFrame): National state table for the same Census year, already compared
            with published totals.

    Returns:
        list[PopulationTableSummary]: Accounting for the tables saved from this archive.

    Raises:
        OSError: Reading an input or writing an output fails.
        ValueError: Population, archive structure, state coverage, or reference checks fail.
        BadZipFile: The source archive is damaged.
        OverflowError: A population count cannot be stored in Parquet.
    """
    census_year, geography_level = describe_nhgis_population_request(request)
    seen_state_codes: set[str] = set()
    summaries = []

    with closing(
        read_nhgis_population_by_state(
            raw_data_directory / request.destination_relative_path, request
        )
    ) as population_tables:
        for population_df in population_tables:
            seen_state_codes.update(population_df[GeographyColumn.STATE_CODE])

            state_code = population_df[GeographyColumn.STATE_CODE].iloc[0]

            comparison = check_nhgis_state_sum(
                population_df, states_df, census_year, geography_level
            )

            output_path = build_population_output_path(census_year, geography_level, state_code)
            save_population_parquet(population_df, population_table_directory / output_path)

            summaries.append(
                summarize_population_table(
                    population_df, request.destination_relative_path, output_path, comparison
                )
            )

    if seen_state_codes != set(STATE_FIPS_CODES) - {"72"}:
        raise ValueError("Historical population archive must cover the 50 states and DC")

    return summaries
