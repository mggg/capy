"""Package complete study-area graphs into independently readable ZIPs below GitHub's file limit."""

import hashlib
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import pandas as pd
from tqdm import tqdm

from capy_core.assign_study_areas.study_area_columns import StudyAreaColumn
from capy_core.geography_types import GeographyLevel

from .archive_inventory import read_graph_archive_summary, read_graph_selection_summary
from .build_area_graph import GraphStatus
from .graph_archives import build_zip_member

TARGET_ARCHIVE_SIZE_BYTES = 80 * 1024**2
MAX_ARCHIVE_SIZE_BYTES = 100 * 1024**2


def publish_graph_archive_parts(
    source_path: Path,
    archive_path: Path,
    *,
    target_size_bytes: int = TARGET_ARCHIVE_SIZE_BYTES,
) -> pd.DataFrame:
    """Repackage a complete ZIP into numbered parts preserving graph and removed-unit CSV bytes.

    Parts are built and checked in a temporary directory before replacing previous parts. The
    source ZIP is never removed here. Each area stays together, in sorted ID order. The 80 MiB
    target leaves room below GitHub's 100 MiB file limit; a single larger area gets its own part
    but still must fit that limit. Recompression is required by Python's ZIP writer.

    Args:
        source_path (Path): Complete ZIP, either a legacy archive or a newly built temporary ZIP.
        archive_path (Path): Unnumbered destination name, used as the base for part01.zip, etc.
        target_size_bytes (int): Positive approximate compressed size per part. Defaults to 80 MiB.

    Returns:
        pd.DataFrame: All area outcomes with their new archive names and total part count.

    Raises:
        OSError: Reading, staging, or publishing fails. The original source remains available.
        ValueError: Inventory or contents disagree, or a part exceeds 100 MiB. ZIP errors propagate.
    """
    if target_size_bytes <= 0:
        raise ValueError("Graph archive target size must be positive")

    with ZipFile(source_path) as source:
        with source.open("summary.csv") as summary_file:
            selection_df = pd.read_csv(summary_file)

        if selection_df.empty:
            raise ValueError(f"Graph archive has an empty summary: {source_path}")

        census_year = int(selection_df.iloc[0].census_year)
        geography_level = GeographyLevel(selection_df.iloc[0].geography_level)
        summary_df = read_graph_archive_summary(source_path, census_year, geography_level)
        summary_df = summary_df.sort_values(StudyAreaColumn.STUDY_AREA_ID).reset_index(drop=True)
        part_summaries = group_areas_into_parts(source, summary_df, target_size_bytes)
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        with TemporaryDirectory(
            prefix=".graph-package-", dir=archive_path.parent
        ) as temporary_name:
            staging_directory = Path(temporary_name)

            for number, part_summary_df in enumerate(
                tqdm(
                    part_summaries, desc=f"Packaging {archive_path.stem}", unit="part", disable=None
                ),
                start=1,
            ):
                part_path = staging_directory / f"{archive_path.stem}_part{number:02d}.zip"
                write_archive_part(source, part_path, part_summary_df, len(part_summaries))
                check_repackaged_members(source, part_path)

            saved_summary_df = read_graph_selection_summary(
                staging_directory / archive_path.name, census_year, geography_level
            )
            accounting_columns = summary_df.columns.difference(["archive", "archive_part_count"])
            pd.testing.assert_frame_equal(
                summary_df[accounting_columns],
                saved_summary_df[accounting_columns],
                check_dtype=False,
            )

            # Remove old parts only once every replacement is complete. Missing parts after an
            # interrupted publication fail the part-count check on the next run.
            for previous_path in archive_path.parent.glob(f"{archive_path.stem}_part*.zip"):
                previous_path.unlink()

            for part_path in sorted(staging_directory.glob("*.zip")):
                part_path.replace(archive_path.parent / part_path.name)

    return saved_summary_df


def area_archive_members(summary: pd.Series) -> list[str]:
    """Return the files belonging to one area, including fully filtered areas' population CSVs."""
    area_id = summary[StudyAreaColumn.STUDY_AREA_ID]
    status = GraphStatus(summary.status)

    if status in (GraphStatus.NO_UNITS_SELECTED, GraphStatus.HISTORICAL_COVERAGE_UNAVAILABLE):
        return []

    members = [f"removed_units/{area_id}.csv"]

    if status == GraphStatus.READY:
        members.insert(0, f"graphs/{area_id}.json")

    return members


def group_areas_into_parts(
    archive: ZipFile, summary_df: pd.DataFrame, target_size_bytes: int
) -> list[pd.DataFrame]:
    """Group whole areas by compressed member sizes, allowing room for summaries and ZIP headers.

    Args:
        archive (ZipFile): Open source ZIP with complete graph and removed-unit members.
        summary_df (pd.DataFrame): Nonempty inventory in the desired area order.
        target_size_bytes (int): Desired compressed size per part; oversized areas stand alone.

    Returns:
        list[pd.DataFrame]: Consecutive, nonempty slices covering every inventory row once.

    Raises:
        ValueError: Files are missing or do not belong to the supplied inventory.
    """
    part_summaries = []
    first_row = 0
    part_size = 0
    expected_members = {"summary.csv"}

    for row_number, (_, summary) in enumerate(summary_df.iterrows()):
        members = area_archive_members(summary)
        expected_members.update(members)
        # Budget uncompressed summary text plus generous per-member ZIP header space.
        area_size = len(summary.to_csv().encode()) + 4096

        for member_name in members:
            area_size += archive.getinfo(member_name).compress_size + 512

        if row_number > first_row and part_size + area_size > target_size_bytes:
            part_summaries.append(summary_df.iloc[first_row:row_number].copy())
            first_row = row_number
            part_size = 0

        part_size += area_size

    if set(archive.namelist()) != expected_members:
        raise ValueError("Graph archive contains files outside its area inventory")

    part_summaries.append(summary_df.iloc[first_row:].copy())

    return part_summaries


def write_archive_part(
    source: ZipFile, part_path: Path, summary_df: pd.DataFrame, part_count: int
) -> None:
    """Stream an area's existing bytes into a part and write its local inventory.

    Args:
        source (ZipFile): Open source ZIP, left unchanged.
        part_path (Path): Temporary destination owned by the packaging operation.
        summary_df (pd.DataFrame): This part's area rows, left unchanged.
        part_count (int): Total number of parts required for this selection.

    Raises:
        OSError: Reading or writing fails.
        ValueError: The resulting file exceeds the 100 MiB publication limit.
    """
    with ZipFile(part_path, "w") as destination:
        for _, summary in summary_df.iterrows():
            for member_name in area_archive_members(summary):
                with (
                    source.open(member_name) as source_file,
                    destination.open(
                        build_zip_member(member_name), "w", force_zip64=True
                    ) as output,
                ):
                    shutil.copyfileobj(source_file, output)

        part_summary_df = summary_df.assign(archive=part_path.name, archive_part_count=part_count)
        destination.writestr(build_zip_member("summary.csv"), part_summary_df.to_csv(index=False))

    if part_path.stat().st_size >= MAX_ARCHIVE_SIZE_BYTES:
        raise ValueError(
            f"Graph part exceeds 100 MiB; its areas need different packaging: {part_path}"
        )


def check_repackaged_members(source: ZipFile, part_path: Path) -> None:
    """Read back every graph/CSV and require its bytes to match the source before publication.

    Args:
        source (ZipFile): Original archive, left open and unchanged.
        part_path (Path): Completed temporary part with a deliberately updated summary.

    Raises:
        ValueError: A graph or population CSV changed during repackaging.
        OSError: Reading fails. ZIP checksum errors propagate.
    """
    with ZipFile(part_path) as part:
        for member_name in part.namelist():
            if member_name == "summary.csv":
                continue

            with source.open(member_name) as original, part.open(member_name) as saved:
                original_digest = hashlib.file_digest(original, "sha256").digest()
                saved_digest = hashlib.file_digest(saved, "sha256").digest()

            if original_digest != saved_digest:
                raise ValueError(f"Repackaging changed {member_name}: {part_path}")
