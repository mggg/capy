"""Process selected Census and NHGIS population files and save their population accounting."""

from contextlib import closing
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd
from tqdm import tqdm

from capy_core.geography_types import GeographyLevel
from capy_core.pipeline_config import PipelineConfig
from capy_core.population_table_columns import GeographyColumn
from capy_core.retrieve_data.census.build_published_file_requests import (
    CENSUS_RESIDENT_TOTALS_FILENAME,
    HISTORICAL_STUDY_TOTALS_FILENAMES,
)
from capy_core.retrieve_data.nhgis.identifiers import NhgisGeographyLevel
from capy_core.retrieve_data.prepare_file_requests import (
    build_raw_file_requests,
    select_raw_file_requests,
)
from capy_core.retrieve_data.raw_file_requests import CensusFileRequest, NhgisTableFileRequest
from capy_core.retrieve_data.state_codes import STATE_FIPS_CODES

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
    build_population_output_path,
    save_population_parquet,
    save_population_summary,
    summarize_population_table,
)


def process_population_tables(
    config: PipelineConfig, repository_root: Path
) -> list[PopulationTableSummary]:
    """Process population inputs using the configured folders and raw-file selections.

    Required state tables and published resident totals are read even if filename filters omit
    them. Historical tables use their corresponding NHGIS states and published workbooks. This
    command never downloads files or reads boundaries. Diagnostic extracts remain join-stage inputs.

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
    census_requests, nhgis_requests = select_population_requests(config)
    raw_directory = (repository_root / config.raw_data_directory).resolve()
    output_directory = (repository_root / config.processed_population_directory).resolve()

    if output_directory.is_relative_to(raw_directory) or raw_directory.is_relative_to(
        output_directory
    ):
        raise ValueError("Raw and processed population folders must be separate, without nesting")

    remove_selected_population_outputs(census_requests, nhgis_requests, output_directory)
    summaries = process_census_population_tables(
        census_requests, config, raw_directory, output_directory
    )

    reference_directory = raw_directory / config.raw_data_subdirectories.population_reference_tables

    summaries.extend(
        process_historical_population_tables(
            nhgis_requests, raw_directory, output_directory, reference_directory
        )
    )
    save_population_summary(summaries, output_directory / "processing_summary.csv")

    return summaries


def remove_selected_population_outputs(
    census_requests: list[CensusFileRequest],
    nhgis_requests: list[NhgisTableFileRequest],
    output_directory: Path,
) -> None:
    """Remove selected derived tables and the summary so stale results cannot survive a rerun.

    Historical archives cover the 50 states and DC; their expected output names are known before
    reading. Validate every destination before removing any file. Other selections remain intact.

    Args:
        census_requests (list[CensusFileRequest]): Selected modern inputs and state references.
        nhgis_requests (list[NhgisTableFileRequest]): Selected historical population archives.
        output_directory (Path): Resolved root for processed files, separate from raw inputs.

    Raises:
        ValueError: An output resolves outside the configured folder.
        OSError: A selected file cannot be removed.
    """
    summary_path = output_directory / "processing_summary.csv"
    output_paths = [
        output_directory
        / build_population_output_path(
            request.census_year, request.geography_level, request.state_code
        )
        for request in census_requests
    ]

    for request in nhgis_requests:
        census_year, geography_level = describe_nhgis_population_request(request)
        state_codes = (
            (None,)
            if geography_level == GeographyLevel.STATE
            else tuple(state_code for state_code in STATE_FIPS_CODES if state_code != "72")
        )
        output_paths.extend(
            output_directory
            / build_population_output_path(census_year, geography_level, state_code)
            for state_code in state_codes
        )

    for output_path in [summary_path, *output_paths]:
        if not output_path.resolve().is_relative_to(output_directory):
            raise ValueError(
                f"Processed output resolves outside its configured folder: {output_path}"
            )

    for output_path in [summary_path, *output_paths]:
        output_path.unlink(missing_ok=True)


def process_census_population_tables(
    census_requests: list[CensusFileRequest],
    config: PipelineConfig,
    raw_directory: Path,
    output_directory: Path,
) -> list[PopulationTableSummary]:
    """Check modern state references, then process each selected Census PL/SF1 table.

    Args:
        census_requests (list[CensusFileRequest]): Selected population inputs and state references.
        config (PipelineConfig): Configured location of the published resident-population CSV.
        raw_directory (Path): Configured raw-data root.
        output_directory (Path): Separate derived-population root.

    Returns:
        list[PopulationTableSummary]: Accounting for each saved national/state Parquet table.

    Raises:
        OSError: An input or published reference cannot be read.
        ValueError: Population checks or writing a table fails; errors identify its input.
    """
    state_requests = [
        request for request in census_requests if request.geography_level == GeographyLevel.STATE
    ]
    state_tables_by_year = load_checked_state_references(raw_directory, config, state_requests)

    summaries = []
    for request in tqdm(census_requests, desc="Population tables", unit="table", disable=None):
        try:
            if request.geography_level == GeographyLevel.STATE:
                population_df = state_tables_by_year[request.census_year]
            else:
                population_df = read_census_population(
                    raw_directory / request.destination_relative_path, request
                )

            check_population_state_sum(
                population_df, request, state_tables_by_year[request.census_year]
            )
            output_path = build_population_output_path(
                request.census_year, request.geography_level, request.state_code
            )
            save_population_parquet(population_df, output_directory / output_path)

        except (OSError, ValueError, OverflowError, BadZipFile) as error:
            raise ValueError(f"{request.destination_relative_path}: {error}") from error

        comparison = PopulationComparison.CENSUS_COUNTS_MATCH_STATE

        if request.geography_level == GeographyLevel.PLACE:
            comparison = PopulationComparison.PLACES_DO_NOT_PARTITION_STATE
        elif request.geography_level == GeographyLevel.STATE:
            comparison = PopulationComparison.RESIDENT_TOTALS_MATCH_PUBLISHED

        summaries.append(
            summarize_population_table(
                population_df, request.destination_relative_path, output_path, comparison
            )
        )

    return summaries


def select_population_requests(
    config: PipelineConfig,
) -> tuple[list[CensusFileRequest], list[NhgisTableFileRequest]]:
    """Select Census and NHGIS populations, adding the state references needed for checks.

    Args:
        config (PipelineConfig): Shared year, level, study-area, and filename selections.

    Returns:
        tuple[list[CensusFileRequest], list[NhgisTableFileRequest]]: Modern and historical inputs,
            each including the needed state references once.

    Raises:
        ValueError: Selections contain no population tables or use unsupported NHGIS datasets.
    """
    available_requests = build_raw_file_requests(config)
    selected_requests = select_raw_file_requests(available_requests, config.file_path_patterns)
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

    census_years = {request.census_year for request in census_requests}
    nhgis_datasets = {request.dataset_name for request in nhgis_requests}

    for request in available_requests:
        if (
            isinstance(request, CensusFileRequest)
            and request.census_year in census_years
            and request.geography_level == GeographyLevel.STATE
            and request not in census_requests
        ):
            census_requests.append(request)
        elif (
            isinstance(request, NhgisTableFileRequest)
            and request.dataset_name in nhgis_datasets
            and request.geographic_levels == (NhgisGeographyLevel.STATE,)
            and request not in nhgis_requests
        ):
            nhgis_requests.append(request)

    census_requests.sort(key=lambda request: request.destination_relative_path)
    # Keep national state tables first in the output summary.
    nhgis_requests.sort(
        key=lambda request: (
            request.geographic_levels != (NhgisGeographyLevel.STATE,),
            request.destination_relative_path,
        )
    )
    return census_requests, nhgis_requests


def load_checked_state_references(
    raw_directory: Path, config: PipelineConfig, state_requests: list[CensusFileRequest]
) -> dict[int, pd.DataFrame]:
    """Read the small state tables and compare them with published resident population totals.

    Args:
        raw_directory (Path): Resolved raw-data root.
        config (PipelineConfig): Folder containing the published population references.
        state_requests (list[CensusFileRequest]): One national state table per needed Census year.

    Returns:
        dict[int, pd.DataFrame]: Validated state tables keyed by Census year.

    Raises:
        OSError: A reference file is missing or unreadable.
        ValueError: A reference fails its structure, count, coverage, or total checks.
    """
    published_totals_csv_path = (
        raw_directory
        / config.raw_data_subdirectories.population_reference_tables
        / CENSUS_RESIDENT_TOTALS_FILENAME
    )
    state_tables_by_year = {}
    for request in state_requests:
        states_df = read_census_population(
            raw_directory / request.destination_relative_path, request
        )
        check_published_state_totals(states_df, published_totals_csv_path, request.census_year)
        state_tables_by_year[request.census_year] = states_df

    return state_tables_by_year


def process_historical_population_tables(
    nhgis_requests: list[NhgisTableFileRequest],
    raw_directory: Path,
    output_directory: Path,
    reference_directory: Path,
) -> list[PopulationTableSummary]:
    """Load and check NHGIS state references, then process each selected historical level.

    State references are loaded before any output is written, regardless of request order.
    Their tables are reused when saving the national state outputs.

    Args:
        nhgis_requests (list[NhgisTableFileRequest]): Population extracts and their state references.
        raw_directory (Path): Configured raw-data root.
        output_directory (Path): Separate derived-population root.
        reference_directory (Path): Configured folder for Census Working Paper 56 workbooks.

    Returns:
        list[PopulationTableSummary]: Accounting for each saved national/state Parquet table.

    Raises:
        ValueError: An archive cannot be read, checked, or saved; the error names its input.
        KeyError: A selected year has no state-reference request.
    """
    state_requests = [
        request
        for request in nhgis_requests
        if request.geographic_levels == (NhgisGeographyLevel.STATE,)
    ]
    state_tables_by_year = load_historical_state_references(
        state_requests, raw_directory, reference_directory
    )

    summaries = []
    for request in tqdm(
        nhgis_requests, desc="NHGIS population archives", unit="archive", disable=None
    ):
        try:
            census_year, geography_level = describe_nhgis_population_request(request)
            states_df = state_tables_by_year[census_year]
            if geography_level == GeographyLevel.STATE:
                output_path = build_population_output_path(census_year, geography_level)
                save_population_parquet(states_df, output_directory / output_path)
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
                        request, raw_directory, output_directory, states_df
                    )
                )
        except (OSError, ValueError, OverflowError, BadZipFile) as error:
            raise ValueError(f"{request.destination_relative_path}: {error}") from error

    return summaries


def load_historical_state_references(
    state_requests: list[NhgisTableFileRequest],
    raw_directory: Path,
    reference_directory: Path,
) -> dict[int, pd.DataFrame]:
    """Read NHGIS state tables and compare their study counts with published Census workbooks.

    Args:
        state_requests (list[NhgisTableFileRequest]): One national state extract per required year.
        raw_directory (Path): Configured raw-data root containing the archives.
        reference_directory (Path): Folder containing Census Working Paper 56 workbooks.

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
                    raw_directory / request.destination_relative_path, request
                )
            ) as population_tables:
                (states_df,) = population_tables

            published_totals_workbook_path = (
                reference_directory / HISTORICAL_STUDY_TOTALS_FILENAMES[census_year]
            )
            check_historical_published_totals(
                states_df, published_totals_workbook_path, census_year
            )
            state_tables_by_year[census_year] = states_df
        except (OSError, ValueError, OverflowError, BadZipFile) as error:
            raise ValueError(f"{request.destination_relative_path}: {error}") from error

    return state_tables_by_year


def process_historical_substate_archive(
    request: NhgisTableFileRequest,
    raw_directory: Path,
    output_directory: Path,
    states_df: pd.DataFrame,
) -> list[PopulationTableSummary]:
    """Compare one substate NHGIS archive with its state reference and save each state's units.

    Reading finishes with a check that all 50 states and DC appeared. If any step fails, the
    archive reader closes; tables already saved remain until the next run removes selected outputs.

    Args:
        request (NhgisTableFileRequest): One national population archive below state level.
        raw_directory (Path): Folder containing the downloaded archive.
        output_directory (Path): Separate folder for processed population tables.
        states_df (pd.DataFrame): National state table for the same Census year, already compared
            with published totals. This function does not change it.

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
        read_nhgis_population_by_state(raw_directory / request.destination_relative_path, request)
    ) as population_tables:
        for population_df in population_tables:
            seen_state_codes.update(population_df[GeographyColumn.STATE_CODE])
            state_code = population_df[GeographyColumn.STATE_CODE].iloc[0]
            comparison = check_nhgis_state_sum(
                population_df, states_df, census_year, geography_level
            )

            output_path = build_population_output_path(census_year, geography_level, state_code)
            save_population_parquet(population_df, output_directory / output_path)
            summaries.append(
                summarize_population_table(
                    population_df, request.destination_relative_path, output_path, comparison
                )
            )

    if seen_state_codes != set(STATE_FIPS_CODES) - {"72"}:
        raise ValueError("Historical population archive must cover the 50 states and DC")

    return summaries
