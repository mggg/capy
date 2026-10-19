"""Identify empty 1990 blocks from original Census STF1B and P.L. 94-171 tables.

The STF1BZ files are Census geographic zero records, supplied in the ten STF1B discs:
https://www2.census.gov/census_1990/stf1b/
California and Connecticut P.L. 94-171 tables also identify empty land blocks absent there:
https://www2.census.gov/census_1990/1990_PL94-171/
"""

from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd
import us

from national_pipeline.retrieve_data.census.build_published_file_requests import (
    PL_1990_REFERENCE_FILENAMES,
    STF1B_1990_ARCHIVE_FILENAMES,
)
from national_pipeline.retrieve_data.state_codes import STATE_FIPS_CODES

BLOCK_REFERENCE_COLUMNS = (
    "SUMLEV",
    "GEOCOMP",
    "STATEFP",
    "CNTY",
    "TRACTBNA",
    "BLCK",
    "POP100",
    "HU100",
)

# This block is in Queens, NY.
# STF1BXNY LOGRECNU 161405 reports 106 people and 52 housing units, agreeing with NHGIS.
# STF1BZNY LOGRECNU 198334 repeats the ID with zero counts and a different centroid/land area.
CONFLICTING_1990_ZERO_BLOCK_ID = "36081077398104"
CONFLICTING_1990_ZERO_BLOCK_POPULATION = 106


def read_1990_zero_population_block_ids(
    block_reference_directory: Path, state_code: str
) -> set[str]:
    """Read original Census evidence for a state's blocks with zero people and housing units.

    The ten STF1B ZIPs remain in their published form. Only the requested state's geographic
    zero DBF is read. California and Connecticut also use their P.L. 94-171 DBFs, where the
    population and housing table cells must agree with the geographic-record totals.
    Repeated zero records contribute one identifier; every occurrence must report both zeros.

    These identifiers establish zero population only for exact matches. A missing identifier
    does not establish that a boundary is empty. Housing is checked as well, so an empty but
    housed block is not classified by this operation. Water-block numbering is handled separately.
    The conflicting Queens, NY reference is excluded: the original population table and NHGIS both
    report 106 residents for that ID, despite its appearance in the geographic-zero file.

    Args:
        block_reference_directory (Path): Folder containing disc1.zip through disc10.zip and the
            California/Connecticut files pl9417ca.dbf and pl9417ct.dbf when those states are used.
        state_code (str): Two-digit state FIPS code for a state or DC, excluding Puerto Rico.

    Returns:
        set[str]: Census block identifiers: two state digits, three county digits, six tract
            digits, and the original three-digit block code with any letter suffix.

    Raises:
        OSError: A required reference cannot be read.
        BadZipFile: A reference ZIP is damaged.
        ValueError: The state, source coverage, identifiers, or population/housing counts are
            inconsistent, or a state's zero DBF is missing or occurs in more than one archive.
    """
    if state_code not in STATE_FIPS_CODES or state_code == "72":
        raise ValueError(f"Unsupported 1990 zero-reference state: {state_code}")

    state_abbreviation = us.states.mapping("fips", "abbr")[state_code]
    zero_table_member_name = f"STF1BZ{state_abbreviation}.DBF"
    matching_archive_paths = []

    for archive_filename in STF1B_1990_ARCHIVE_FILENAMES:
        disc_archive_path = block_reference_directory / archive_filename

        with ZipFile(disc_archive_path) as archive:
            matching_archive_paths.extend(
                disc_archive_path
                for member_name in archive.namelist()
                if member_name == zero_table_member_name
            )

    if len(matching_archive_paths) != 1:
        raise ValueError(f"Expected one STF1B geographic zero table for state {state_code}")

    source_reference_df = gpd.read_file(
        f"zip://{matching_archive_paths[0]}!{zero_table_member_name}",
        ignore_geometry=True,
        columns=pd.Index(BLOCK_REFERENCE_COLUMNS),
    )

    zero_reference_df = source_reference_df.loc[
        source_reference_df["SUMLEV"].eq("100") & source_reference_df["GEOCOMP"].eq("00")
    ].copy()
    zero_reference_block_ids = build_checked_1990_block_ids(zero_reference_df, state_code)

    if not zero_reference_df["POP100"].eq(0).all() or not zero_reference_df["HU100"].eq(0).all():
        raise ValueError(f"STF1B geographic zero table contains nonzero counts for {state_code}")

    zero_block_ids = set(zero_reference_block_ids)
    zero_block_ids.discard(CONFLICTING_1990_ZERO_BLOCK_ID)

    if state_code in PL_1990_REFERENCE_FILENAMES:
        zero_block_ids.update(
            read_1990_pl_zero_block_ids(
                block_reference_directory / PL_1990_REFERENCE_FILENAMES[state_code], state_code
            )
        )

    return zero_block_ids


def read_1990_pl_zero_block_ids(pl_reference_table_path: Path, state_code: str) -> set[str]:
    """Select blocks confirmed empty by both geographic totals and population/housing cells.

    California's original file repeats one zero record. Repeated identifiers are accepted only
    when their population and housing counts agree.

    Args:
        pl_reference_table_path (Path): Original California or Connecticut P.L. 94-171 DBF.
        state_code (str): State expected in its block records.

    Returns:
        set[str]: Unique block IDs having zero people and zero housing units in every occurrence.

    Raises:
        OSError: The reference cannot be read.
        ValueError: Identifiers, geography totals, table cells, or repeated records disagree.
    """
    source_reference_df = gpd.read_file(
        pl_reference_table_path,
        ignore_geometry=True,
        columns=pd.Index([*BLOCK_REFERENCE_COLUMNS, "P001_0001", "H001_0001"]),
    )

    block_reference_df = source_reference_df.loc[
        source_reference_df["SUMLEV"].eq("750") & source_reference_df["GEOCOMP"].eq("00")
    ].copy()
    block_ids = build_checked_1990_block_ids(block_reference_df, state_code)

    if not block_reference_df["POP100"].eq(block_reference_df["P001_0001"]).all() or not (
        block_reference_df["HU100"].eq(block_reference_df["H001_0001"]).all()
    ):
        raise ValueError(f"P.L. 94-171 population/housing cells disagree for {state_code}")

    repeated_counts_df = block_reference_df.loc[
        block_ids.duplicated(keep=False), ["POP100", "HU100"]
    ].assign(STFID=block_ids)
    distinct_counts_df = repeated_counts_df.groupby("STFID")[["POP100", "HU100"]].nunique()

    if distinct_counts_df.gt(1).any().any():
        raise ValueError(f"Repeated P.L. 94-171 block has conflicting counts for {state_code}")

    empty_block_rows = block_reference_df["POP100"].eq(0) & block_reference_df["HU100"].eq(0)

    return set(block_ids.loc[empty_block_rows])


def build_checked_1990_block_ids(block_reference_df: pd.DataFrame, state_code: str) -> pd.Series:
    """Validate source geography/count fields and assemble the original Census block identity.

    Args:
        block_reference_df (pd.DataFrame): Block records selected at the source's whole-area level.
        state_code (str): Two-digit state code expected in every record.

    Returns:
        pd.Series: Census block identifiers with six-digit tract codes.

    Raises:
        ValueError: Records are absent or contain wrong-state, malformed, or missing identifiers
            or noninteger/negative population or housing counts.
    """
    if block_reference_df.empty or not bool(block_reference_df["STATEFP"].eq(state_code).all()):
        raise ValueError(f"Expected 1990 reference block records for state {state_code}")

    for column, pattern in (
        ("STATEFP", r"[0-9]{2}"),
        ("CNTY", r"[0-9]{3}"),
        ("TRACTBNA", r"[0-9]{4,6}"),
        ("BLCK", r"[0-9]{3}[A-Za-z]?"),
    ):
        if (
            not block_reference_df[column]
            .astype("string")
            .str.fullmatch(pattern)
            .fillna(False)
            .all()
        ):
            raise ValueError(f"Invalid {column} in 1990 reference for state {state_code}")

    for column in ("POP100", "HU100"):
        count_values = pd.Series(pd.to_numeric(block_reference_df[column], errors="raise"))

        if count_values.isna().any() or count_values.lt(0).any() or count_values.mod(1).ne(0).any():
            raise ValueError(f"Invalid {column} in 1990 reference for state {state_code}")

    return (
        block_reference_df["STATEFP"]
        + block_reference_df["CNTY"]
        + block_reference_df["TRACTBNA"].str.pad(6, side="right", fillchar="0")
        + block_reference_df["BLCK"]
    )
