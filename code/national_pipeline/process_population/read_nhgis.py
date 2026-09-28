"""Read whole-area NHGIS population tables, keeping their original geographic identities."""

import csv
from collections.abc import Generator
from contextlib import closing
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from national_pipeline.geography_types import GeographyLevel
from national_pipeline.population_table_columns import (
    GeographyColumn,
    PopulationColumn,
    PopulationSourceColumn,
)
from national_pipeline.retrieve_data.nhgis.identifiers import (
    NHGIS_DATASETS_BY_YEAR,
    NHGIS_LEVELS_BY_GEOGRAPHY,
)
from national_pipeline.retrieve_data.nhgis.table_columns import (
    NHGIS_1980_HISPANIC_RACE_COLUMNS,
    NHGIS_1980_INDIGENOUS_ASIAN_PACIFIC_ISLANDER_COLUMNS,
    NHGIS_1980_RACE_COLUMNS,
    NHGIS_1990_RACE_ORIGIN_COLUMNS,
    NHGIS_COUNT_COLUMNS,
    Nhgis1980Column,
    Nhgis1990Column,
    NhgisGeographyColumn,
)
from national_pipeline.retrieve_data.raw_file_requests import NhgisTableFileRequest
from national_pipeline.retrieve_data.state_codes import STATE_FIPS_CODES

NHGIS_POPULATION_LEVELS = {
    nhgis_level: geography_level
    for geography_level, nhgis_level in NHGIS_LEVELS_BY_GEOGRAPHY.items()
}


def describe_nhgis_population_request(request: NhgisTableFileRequest) -> tuple[int, GeographyLevel]:
    """Identify the Census year and geography level of a supported NHGIS population request.

    Both 1980 and 1990 support state, county, and tract tables; only 1990 supports block groups
    and blocks. Geographic correspondence tables, such as place parts, belong to the boundary
    join stage and are rejected here. This checks the request's dataset and level only; the
    archive reader checks its contents and whole-area population columns separately.

    Args:
        request (NhgisTableFileRequest): Extract definition naming one dataset and one geography
            level. Supported datasets are 1980_STF1 and 1990_STF1.

    Returns:
        tuple[int, GeographyLevel]: Census year followed by the corresponding geography enum,
            such as (1990, GeographyLevel.BLOCK_GROUP) for the NHGIS level "blck_grp".

    Raises:
        ValueError: The dataset is unsupported, the request names more or fewer than one level,
            or the level is not supported for that Census year.
    """
    census_years_by_dataset = {dataset: year for year, dataset in NHGIS_DATASETS_BY_YEAR.items()}

    if request.dataset_name not in census_years_by_dataset or len(request.geographic_levels) != 1:
        raise ValueError("Population processing requires one supported NHGIS dataset and level")

    census_year = census_years_by_dataset[request.dataset_name]
    geography_level = NHGIS_POPULATION_LEVELS.get(request.geographic_levels[0])
    supported_levels = {GeographyLevel.STATE, GeographyLevel.COUNTY, GeographyLevel.TRACT}

    if census_year == 1990:
        supported_levels |= {GeographyLevel.BLOCK_GROUP, GeographyLevel.BLOCK}

    if geography_level is None or geography_level not in supported_levels:
        raise ValueError(
            "NHGIS correspondence tables are inputs to geographic joins, not populations"
        )

    return census_year, geography_level


def read_nhgis_population_by_state(
    population_archive_path: Path, request: NhgisTableFileRequest
) -> Generator[pd.DataFrame, None, None]:
    """Read a national archive in chunks and yield one checked population table per state.

    State-reference extracts yield one national table. Other extracts must group their rows by
    state; a state appearing again after another state is an error. Only one state's records and
    a read chunk are accumulated, although all seen GISJOINs are retained to detect duplicates.
    No data rows are excluded, and the ZIP is closed when iteration ends or the caller closes it.

    Wrap this generator in ``with closing(...)``, importing ``closing`` from ``contextlib``.
    It keeps the archive open between yielded tables; the wrapper closes it promptly if a
    caller's population check or file write fails, or the loop stops early.

    Args:
        population_archive_path (Path): Downloaded single-level NHGIS ZIP with its original CSV
            member.
        request (NhgisTableFileRequest): Dataset, level, and relative input filename.

    Yields:
        pd.DataFrame: Source columns, study counts, and source row/member information. Sorted by
            GISJOIN within each output; geographic codes remain strings.

    Raises:
        OSError: The archive cannot be read.
        ValueError: The archive, columns, populations, state order, or identities are invalid.
        BadZipFile: ZIP contents are damaged or cannot be decoded as an archive.
    """
    _, geography_level = describe_nhgis_population_request(request)
    completed_state_codes: set[str] = set()
    current_state_code = None

    state_table_parts = []

    with closing(
        read_nhgis_population_chunks(population_archive_path, request)
    ) as population_chunks:
        for population_chunk_df in population_chunks:
            if geography_level == GeographyLevel.STATE:
                state_table_parts.append(population_chunk_df)
                continue

            # Split at state changes, including changes that occur inside a read chunk.
            state_run_numbers = (
                population_chunk_df[GeographyColumn.STATE_CODE]
                .ne(population_chunk_df[GeographyColumn.STATE_CODE].shift())
                .cumsum()
            )

            for _, state_rows_df in population_chunk_df.groupby(state_run_numbers, sort=False):
                state_code = state_rows_df[GeographyColumn.STATE_CODE].iloc[0]

                if current_state_code is not None and state_code != current_state_code:
                    completed_state_codes.add(current_state_code)

                    yield (
                        pd.concat(state_table_parts)
                        .sort_values(GeographyColumn.GEOGRAPHIC_ID)
                        .reset_index(drop=True)
                    )

                    state_table_parts = []

                if state_code in completed_state_codes:
                    raise ValueError(f"NHGIS rows are not grouped by state: {state_code}")

                current_state_code = state_code
                state_table_parts.append(state_rows_df)

        if not state_table_parts:
            raise ValueError("NHGIS population table contains no data rows")

        yield (
            pd.concat(state_table_parts)
            .sort_values(GeographyColumn.GEOGRAPHIC_ID)
            .reset_index(drop=True)
        )


def read_nhgis_population_chunks(
    population_archive_path: Path,
    request: NhgisTableFileRequest,
) -> Generator[pd.DataFrame, None, None]:
    """Read, validate, and label chunks of a single-level NHGIS CSV inside its ZIP.

    The national 1990 block CSV is about 1.43 GB uncompressed and needs more memory as a pandas
    table. Reading 100,000 rows at a time avoids loading the whole table before the caller can
    assemble and save individual states. Smaller extracts use the same reading path. Memory
    use still grows with the largest state's table and the identifiers retained across chunks
    to detect duplicate GISJOINs.

    Wrap this generator in ``with closing(...)``, importing ``closing`` from ``contextlib``.
    The CSV stream and ZIP stay open between chunks. The wrapper closes both if the caller
    stops iterating early or raises an error while processing a chunk.

    Args:
        population_archive_path (Path): Downloaded population archive.
        request (NhgisTableFileRequest): Expected dataset/level and relative input filename.

    Yields:
        pd.DataFrame: Checked rows in source order with source member and record positions.

    Raises:
        OSError: A source cannot be read.
        ValueError: Source columns, identities, or counts fail validation.
        BadZipFile: The ZIP is damaged.
    """
    census_year, geography_level = describe_nhgis_population_request(request)

    with ZipFile(population_archive_path) as archive:
        csv_member_name, description_row_indexes = inspect_nhgis_population_header(archive, request)

        with archive.open(csv_member_name) as stream:
            source_chunks = pd.read_csv(
                stream,
                dtype=str,
                keep_default_na=False,
                encoding="utf-8-sig",
                skiprows=description_row_indexes,
                chunksize=100_000,
            )

            seen_gisjoins: set[str] = set()
            first_source_row = 1

            for source_chunk_df in source_chunks:
                if not isinstance(source_chunk_df.index, pd.RangeIndex):
                    raise ValueError("NHGIS CSV has more fields than its header")  # noqa: TRY004

                population_chunk_df = normalize_nhgis_population(
                    source_chunk_df, census_year, geography_level
                )
                chunk_gisjoins = set(population_chunk_df[NhgisGeographyColumn.GEOGRAPHIC_ID])

                if len(chunk_gisjoins) != len(population_chunk_df) or seen_gisjoins.intersection(
                    chunk_gisjoins
                ):
                    raise ValueError("Duplicate NHGIS GISJOIN in population archive")

                seen_gisjoins.update(chunk_gisjoins)

                population_chunk_df[PopulationSourceColumn.SOURCE_FILE] = (
                    request.destination_relative_path
                )
                population_chunk_df[PopulationSourceColumn.SOURCE_MEMBER] = csv_member_name
                population_chunk_df[PopulationSourceColumn.SOURCE_ROW] = range(
                    first_source_row, first_source_row + len(population_chunk_df)
                )
                first_source_row += len(population_chunk_df)

                yield population_chunk_df


def inspect_nhgis_population_header(
    archive: ZipFile, request: NhgisTableFileRequest
) -> tuple[str, list[int]]:
    """Find the single requested CSV and recognize its optional descriptive header row.

    Args:
        archive (ZipFile): Open population ZIP, owned by the caller.
        request (NhgisTableFileRequest): Expected dataset and single geography level.

    Returns:
        tuple[str, list[int]]: CSV member name and rows pandas should skip. The description row
            is skipped only when both GISJOIN and YEAR identify it as a header.

    Raises:
        ValueError: CSV members, required columns, or whole-area count columns do not match.
    """
    census_year, _ = describe_nhgis_population_request(request)
    dataset_code = "ds104" if census_year == 1980 else "ds120"
    expected_csv_suffix = f"_{dataset_code}_{census_year}_{request.geographic_levels[0]}.csv"
    csv_member_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]

    if len(csv_member_names) != 1 or not csv_member_names[0].endswith(expected_csv_suffix):
        raise ValueError(
            f"Expected exactly one NHGIS population CSV ending in {expected_csv_suffix}"
        )

    with (
        archive.open(csv_member_names[0]) as stream,
        TextIOWrapper(stream, encoding="utf-8-sig") as text,
    ):
        reader = csv.reader(text)
        header = next(reader, [])
        first_row = next(reader, [])

    required_columns = {
        NhgisGeographyColumn.GEOGRAPHIC_ID,
        NhgisGeographyColumn.CENSUS_YEAR,
        NhgisGeographyColumn.STATE_CODE,
        *NHGIS_COUNT_COLUMNS[census_year],
    }

    if len(header) != len(set(header)) or not required_columns.issubset(header):
        raise ValueError("Missing or duplicate NHGIS population columns")

    population_columns = {
        name for name in header if name.startswith(("C7L", "C9D", "C9F", "C9G", "ET1", "ET2"))
    }

    if population_columns != set(NHGIS_COUNT_COLUMNS[census_year]):
        raise ValueError("Expected whole-area population columns without additional breakdowns")

    description_row_indexes = []

    if (
        len(first_row) == len(header)
        and first_row[header.index(NhgisGeographyColumn.GEOGRAPHIC_ID)] == "GIS Join Match Code"
        and first_row[header.index(NhgisGeographyColumn.CENSUS_YEAR)] == "Data File Year"
    ):
        description_row_indexes = [1]

    return csv_member_names[0], description_row_indexes


def normalize_nhgis_population(
    source_population_df: pd.DataFrame, census_year: int, geography_level: GeographyLevel
) -> pd.DataFrame:
    """Check one chunk and derive non-Hispanic White, non-Hispanic Black, and POC counts.

    GISJOIN becomes GEOID verbatim. Geographic correspondence, including known malformed source
    labels and special tract/block codes, is resolved at the boundary-join stage, not guessed here.
    Blank or nonnumeric counts are errors. Suppression flags and blank geographic context are
    preserved as supplied; this reader does not interpret the flags or replace reported counts.

    Args:
        source_population_df (pd.DataFrame): String-valued source records for one supported year and
            level.
        census_year (int): 1980 or 1990.
        geography_level (GeographyLevel): State, county, tract, or supported 1990 block/group level.

    Returns:
        pd.DataFrame: A copy with exact integer counts and derived population/identity fields.

    Raises:
        ValueError: Year, state, required county code, source ID, or population values are invalid.
    """
    population_df = source_population_df.copy()

    if not pd.Series(population_df[NhgisGeographyColumn.CENSUS_YEAR]).eq(str(census_year)).all():
        raise ValueError(f"NHGIS table contains records outside {census_year}")

    if (
        not pd.Series(population_df[NhgisGeographyColumn.STATE_CODE])
        .isin([state_code for state_code in STATE_FIPS_CODES if state_code != "72"])
        .all()
    ):
        raise ValueError("Historical population records must identify one of the 50 states or DC")

    if population_df[NhgisGeographyColumn.GEOGRAPHIC_ID].fillna("").str.strip().eq("").any():
        raise ValueError("NHGIS population record has no GISJOIN")

    if geography_level != GeographyLevel.STATE and (
        NhgisGeographyColumn.COUNTY_CODE not in population_df
        or not population_df[NhgisGeographyColumn.COUNTY_CODE]
        .str.fullmatch(r"[0-9]{3}", na=False)
        .all()
    ):
        raise ValueError("NHGIS substate records require three-digit county codes")

    for population_column in NHGIS_COUNT_COLUMNS[census_year]:
        count_strings = population_df[population_column]

        if not count_strings.str.fullmatch(r"[0-9]+", na=False).all():
            raise ValueError(
                f"{population_column} must contain nonnegative integer counts in every row"
            )

        population_df[population_column] = pd.Series(
            [int(count_string) for count_string in count_strings],
            index=population_df.index,
            dtype=object,
        )

    if census_year == 1980:
        study_counts_df = derive_1980_population_counts(population_df)
        population_df[study_counts_df.columns] = study_counts_df
    else:
        if (
            not population_df[list(NHGIS_1990_RACE_ORIGIN_COLUMNS)]
            .sum(axis=1)
            .eq(population_df[Nhgis1990Column.TOTAL])
            .all()
        ):
            raise ValueError("1990 race/origin categories do not sum to total population")

        population_df[PopulationColumn.TOTAL] = population_df[Nhgis1990Column.TOTAL]
        population_df[PopulationColumn.NON_HISPANIC_WHITE] = population_df[
            Nhgis1990Column.NON_HISPANIC_WHITE
        ]
        population_df[PopulationColumn.NON_HISPANIC_BLACK] = population_df[
            Nhgis1990Column.NON_HISPANIC_BLACK
        ]

    population_df[PopulationColumn.POC] = (
        population_df[PopulationColumn.TOTAL] - population_df[PopulationColumn.NON_HISPANIC_WHITE]
    )

    population_df[GeographyColumn.GEOGRAPHIC_ID] = population_df[NhgisGeographyColumn.GEOGRAPHIC_ID]
    population_df[GeographyColumn.STATE_CODE] = population_df[NhgisGeographyColumn.STATE_CODE]
    population_df[PopulationSourceColumn.CENSUS_YEAR] = census_year
    population_df[PopulationSourceColumn.CENSUS_DATASET] = NHGIS_DATASETS_BY_YEAR[census_year].value
    population_df[GeographyColumn.GEOGRAPHY_LEVEL] = geography_level.value

    return population_df


def derive_1980_population_counts(population_df: pd.DataFrame) -> pd.DataFrame:
    """Check STF1 race/origin identities and return the three derived study counts.

    The four Hispanic race cells must fit their corresponding race groups. The combined
    American Indian/Asian/Pacific Islander cell corresponds to NT7 cells 3 through 14.
    Source: NT1A, NT7, NT9A, and NT9B definitions in the 1980_STF1 extract codebook.

    Args:
        population_df (pd.DataFrame): Exact integer count columns, already checked as nonnegative.
            The table remains unchanged on success and failure.

    Returns:
        pd.DataFrame: TOTPOP, WHITE, and BLACK columns with the original row index. POC is
            calculated by the normalizer for both historical years.

    Raises:
        ValueError: Race totals, Hispanic totals, or Hispanic subset bounds disagree.
    """
    race_counts_df = population_df[list(NHGIS_1980_RACE_COLUMNS)]
    hispanic_race_counts_df = population_df[list(NHGIS_1980_HISPANIC_RACE_COLUMNS)]

    if not race_counts_df.sum(axis=1).eq(population_df[Nhgis1980Column.TOTAL]).all():
        raise ValueError("1980 race counts do not sum to total population")

    if (
        not hispanic_race_counts_df.sum(axis=1)
        .eq(population_df[Nhgis1980Column.HISPANIC_TOTAL])
        .all()
    ):
        raise ValueError("1980 Hispanic race counts do not sum to Hispanic population")

    race_totals_by_hispanic_column = {
        Nhgis1980Column.HISPANIC_WHITE: population_df[Nhgis1980Column.WHITE],
        Nhgis1980Column.HISPANIC_BLACK: population_df[Nhgis1980Column.BLACK],
        Nhgis1980Column.HISPANIC_INDIGENOUS_ASIAN_PACIFIC_ISLANDER: population_df[
            list(NHGIS_1980_INDIGENOUS_ASIAN_PACIFIC_ISLANDER_COLUMNS)
        ].sum(axis=1),
        Nhgis1980Column.HISPANIC_OTHER_RACE: population_df[Nhgis1980Column.OTHER_RACE],
    }

    for hispanic_column, race_total in race_totals_by_hispanic_column.items():
        if (population_df[hispanic_column] > race_total).any():
            raise ValueError("1980 Hispanic race count exceeds its corresponding race population")

    return pd.DataFrame(
        {
            PopulationColumn.TOTAL: population_df[Nhgis1980Column.TOTAL],
            PopulationColumn.NON_HISPANIC_WHITE: (
                population_df[Nhgis1980Column.WHITE] - population_df[Nhgis1980Column.HISPANIC_WHITE]
            ),
            PopulationColumn.NON_HISPANIC_BLACK: (
                population_df[Nhgis1980Column.BLACK] - population_df[Nhgis1980Column.HISPANIC_BLACK]
            ),
        },
        index=population_df.index,
    )
