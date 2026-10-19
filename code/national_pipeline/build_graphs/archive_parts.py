"""Write complete study-area graphs directly into size-limited, independently readable ZIP parts."""

from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import pandas as pd

from national_pipeline.geography_types import GeographyLevel
from national_pipeline.population_table_columns import PopulationColumn

from .archive_inventory import read_graph_selection_summary
from .build_area_graph import AreaGraphFiles
from .graph_archives import build_zip_member, write_file_to_archive

TARGET_ARCHIVE_SIZE_BYTES = 80 * 1024**2
MAX_ARCHIVE_SIZE_BYTES = 100 * 1024**2


def publish_graph_archive_parts(
    archive_path: Path, area_files: list[AreaGraphFiles], temporary_directory: Path
) -> pd.DataFrame:
    """Compress completed area files into checked parts, then replace the previous selection.

    Each area's files stay together in the supplied order. Start a new part after reaching the
    80 MiB target; whole areas can exceed that target, but every finalized part must stay below
    100 MiB. If a multi-area part exceeds the limit, staging retries with a smaller target. A
    single area that cannot fit stops publication. Parts are checked before any previous parts
    are removed. Publication replaces files individually; an interruption can leave missing parts,
    which the next build detects through each part's saved total part count and rebuilds.

    Args:
        archive_path (Path): Base ZIP name used to name numbered parts, not itself written.
        area_files (list[AreaGraphFiles]): Nonempty completed worker results in study-area ID order.
        temporary_directory (Path): Selection-owned folder containing completed JSON/CSV files.

    Returns:
        pd.DataFrame: All area outcomes, with the archive name and total part count for each row.

    Raises:
        OSError: Reading, staging, or publishing fails. Prior parts survive staging failures.
        ValueError: Inventory or accounting disagree, or an area cannot fit below 100 MiB.
            ZIP errors propagate. The caller retains ownership of the source area files.
    """
    summary_df = build_graph_archive_summary(area_files)
    census_year = int(summary_df.iloc[0].census_year)
    geography_level = GeographyLevel(summary_df.iloc[0].geography_level)
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory(prefix=".graph-package-", dir=archive_path.parent) as temporary_name:
        staging_directory = Path(temporary_name)
        part_summaries = write_size_limited_graph_parts(
            archive_path, area_files, summary_df, temporary_directory, staging_directory
        )

        for part_summary_df in part_summaries:
            part_path = staging_directory / str(part_summary_df.iloc[0].archive)

            with ZipFile(part_path) as archive:
                damaged_member = archive.testzip()

            if damaged_member is not None:
                raise ValueError(f"Damaged graph member {damaged_member}: {part_path.name}")

        saved_summary_df = read_graph_selection_summary(
            staging_directory / archive_path.name, census_year, geography_level
        )
        try:
            pd.testing.assert_frame_equal(
                summary_df.convert_dtypes(),
                saved_summary_df[summary_df.columns].convert_dtypes(),
                check_dtype=False,
            )
        except AssertionError as error:
            raise ValueError(
                f"Saved graph accounting differs from worker results: {archive_path}"
            ) from error

        # Remove the old set before replacing any parts so interruption cannot mix generations.
        for previous_path in archive_path.parent.glob(f"{archive_path.stem}_part*.zip"):
            previous_path.unlink()

        for part_summary_df in part_summaries:
            part_path = staging_directory / str(part_summary_df.iloc[0].archive)
            part_path.replace(archive_path.parent / part_path.name)

    return saved_summary_df


def build_graph_archive_summary(area_files: list[AreaGraphFiles]) -> pd.DataFrame:
    """Collect worker accounting with nullable integer counts for unavailable historical areas."""
    summary_df = pd.DataFrame([area.summary for area in area_files])
    count_columns = [
        "node_count",
        "edge_count",
        "input_unit_count",
        "removed_unit_count",
        "initial_component_count",
        "artificial_edge_count",
        *(
            f"{group}_{column}"
            for group in ("input", "retained", "removed")
            for column in PopulationColumn
        ),
    ]
    summary_df[count_columns] = summary_df[count_columns].astype("Int64")

    return summary_df


def write_size_limited_graph_parts(
    archive_path: Path,
    area_files: list[AreaGraphFiles],
    summary_df: pd.DataFrame,
    temporary_directory: Path,
    staging_directory: Path,
) -> list[pd.DataFrame]:
    """Write parts with final summaries, retrying a smaller target when whole areas overshoot.

    Args:
        archive_path (Path): Base name for numbered ZIP parts.
        area_files (list[AreaGraphFiles]): Completed files in the same order as summary_df.
        summary_df (pd.DataFrame): Area accounting with nullable integer counts.
        temporary_directory (Path): Folder containing the completed area files.
        staging_directory (Path): Empty folder owned by the publishing operation. Failed size
            attempts are removed before retrying; the owner cleans up on exceptions.

    Returns:
        list[pd.DataFrame]: Inventories of finalized parts, all below the publication limit.

    Raises:
        OSError: Reading or writing fails.
        ValueError: A single area cannot fit, or the smallest target still exceeds the limit.
    """
    target_size_bytes = TARGET_ARCHIVE_SIZE_BYTES

    while True:
        part_summaries = write_graph_member_parts(
            archive_path,
            area_files,
            summary_df,
            temporary_directory,
            staging_directory,
            target_size_bytes=target_size_bytes,
        )
        oversized_part_found = False

        for part_summary_df in part_summaries:
            part_path = staging_directory / str(part_summary_df.iloc[0].archive)
            part_summary_df["archive_part_count"] = len(part_summaries)

            with ZipFile(part_path, "a") as archive:
                archive.writestr(
                    build_zip_member("summary.csv"), part_summary_df.to_csv(index=False)
                )

            if part_path.stat().st_size >= MAX_ARCHIVE_SIZE_BYTES:
                if len(part_summary_df) == 1 or target_size_bytes == 1:
                    raise ValueError(
                        f"Graph part cannot fit below the 100 MiB publication limit: {part_path.name}"
                    )
                oversized_part_found = True

        if not oversized_part_found:
            return part_summaries

        for part_summary_df in part_summaries:
            (staging_directory / str(part_summary_df.iloc[0].archive)).unlink()

        target_size_bytes = max(1, target_size_bytes // 2)


def write_graph_member_parts(
    archive_path: Path,
    area_files: list[AreaGraphFiles],
    summary_df: pd.DataFrame,
    temporary_directory: Path,
    staging_directory: Path,
    *,
    target_size_bytes: int,
) -> list[pd.DataFrame]:
    """Write whole areas until each part reaches the target, leaving summaries for finalization.

    Args:
        archive_path (Path): Base name for numbered ZIP parts.
        area_files (list[AreaGraphFiles]): Completed files in the same order as summary_df.
        summary_df (pd.DataFrame): Area accounting with nullable integer counts.
        temporary_directory (Path): Folder containing the completed area files.
        staging_directory (Path): Empty staging folder owned by the publishing operation.
        target_size_bytes (int): Positive compressed-size target, checked after each whole area.

    Returns:
        list[pd.DataFrame]: Each part's area rows and filename, in publication order.
            Total part counts can be added after all graph members have been written.

    Raises:
        OSError: Reading an area file or writing a staged ZIP fails.
    """
    remaining_areas = iter(area_files)
    part_summaries = []
    written_area_count = 0

    while written_area_count < len(area_files):
        part_path = staging_directory / f"{archive_path.stem}_part{len(part_summaries) + 1:02d}.zip"
        first_area_index = written_area_count

        with part_path.open("wb") as output, ZipFile(output, "w") as archive:
            for area in remaining_areas:
                for member_path in area.member_paths:
                    write_file_to_archive(archive, member_path, temporary_directory)

                written_area_count += 1

                if output.tell() >= target_size_bytes:
                    break

        part_summaries.append(
            summary_df.iloc[first_area_index:written_area_count].assign(archive=part_path.name)
        )

    return part_summaries
