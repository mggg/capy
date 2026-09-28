"""Read graph ZIP inventories and locate complete sets of numbered archive parts."""

from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from national_pipeline.assign_study_areas.study_area_columns import (
    MembershipColumn,
    StudyAreaColumn,
)
from national_pipeline.geography_types import GeographyLevel

from .build_area_graph import GraphStatus


def read_graph_archive_summary(
    archive_path: Path, census_year: int, geography_level: GeographyLevel
) -> pd.DataFrame:
    """Read an archive's area inventory and require its ready entries to match its graph members.

    Args:
        archive_path (Path): Selected graph ZIP, read without extracting any members.
        census_year (int): Expected year of graph-node population and boundaries.
        geography_level (GeographyLevel): Expected graph-node resolution.

    Returns:
        pd.DataFrame: One outcome per area, including areas without graphs. This checks the
            inventory; graph contents and population accounting are checked when each graph loads.

    Raises:
        OSError: The archive cannot be read.
        ValueError: Summary identities, statuses, selections, or graph-member inventory disagree.
            ZIP, CSV, and missing-member errors propagate to the stage runner.
    """
    with ZipFile(archive_path) as archive:
        member_names = archive.namelist()

        with archive.open("summary.csv") as summary_file:
            summary_df = pd.read_csv(summary_file, dtype={StudyAreaColumn.STUDY_AREA_ID: str})

    area_ids = summary_df[StudyAreaColumn.STUDY_AREA_ID]

    if summary_df.empty or bool(area_ids.isna().any()) or bool(area_ids.duplicated().any()):
        raise ValueError(f"Graph summary needs one identified outcome per area: {archive_path}")

    if not bool(summary_df[MembershipColumn.CENSUS_YEAR].eq(census_year).all()) or not bool(
        summary_df[MembershipColumn.GEOGRAPHY_LEVEL].eq(geography_level).all()
    ):
        raise ValueError(f"Graph summary disagrees with requested year or level: {archive_path}")

    if not bool(summary_df[MembershipColumn.STATUS].isin(list(GraphStatus)).all()):
        raise ValueError(f"Graph summary contains an unsupported status: {archive_path}")

    ready_mask = summary_df[MembershipColumn.STATUS].eq(GraphStatus.READY)
    expected_graph_members = "graphs/" + area_ids[ready_mask] + ".json"

    if (
        len(member_names) != len(set(member_names))
        or not summary_df.loc[ready_mask, "graph_member"].eq(expected_graph_members).all()
        or summary_df.loc[~ready_mask, "graph_member"].notna().any()
        or {name for name in member_names if name.startswith("graphs/")}
        != set(expected_graph_members)
    ):
        raise ValueError(f"Graph members disagree with archive accounting: {archive_path}")

    return summary_df


def read_graph_selection_summary(
    archive_path: Path, census_year: int, geography_level: GeographyLevel
) -> pd.DataFrame:
    """Read one legacy ZIP or every numbered part for a year/level, rejecting incomplete sets.

    A legacy ZIP takes precedence while its replacement parts are being published. Each numbered
    part records the total part count in its summary, so a missing last part cannot pass as complete.

    Args:
        archive_path (Path): Original unnumbered ZIP name; also the base name for numbered parts.
        census_year (int): Expected population year.
        geography_level (GeographyLevel): Expected graph-node resolution.

    Returns:
        pd.DataFrame: One row per area, with the actual ZIP filename in archive.

    Raises:
        FileNotFoundError: No archive exists for this selection.
        ValueError: Parts are missing, repeated, inconsistent, or have overlapping area inventories.
            ZIP and summary parsing errors propagate.
    """
    if archive_path.exists():
        return read_graph_archive_summary(archive_path, census_year, geography_level).assign(
            archive=archive_path.name
        )

    part_paths = list(archive_path.parent.glob(f"{archive_path.stem}_part*.zip"))

    if not part_paths:
        raise FileNotFoundError(f"No graph archives for {archive_path}")

    expected_paths = [
        archive_path.with_stem(f"{archive_path.stem}_part{number:02d}")
        for number in range(1, len(part_paths) + 1)
    ]

    if set(part_paths) != set(expected_paths):
        raise ValueError(f"Graph archive part numbers are not consecutive: {archive_path}")

    summaries = []

    for part_path in expected_paths:
        summary_df = read_graph_archive_summary(part_path, census_year, geography_level)

        if (
            "archive_part_count" not in summary_df
            or not summary_df.archive_part_count.eq(len(part_paths)).all()
        ):
            raise ValueError(f"Incomplete or inconsistent graph archive parts: {archive_path}")

        summaries.append(summary_df.assign(archive=part_path.name))

    summary_df = pd.concat(summaries, ignore_index=True)

    if summary_df[StudyAreaColumn.STUDY_AREA_ID].duplicated().any():
        raise ValueError(f"Study areas repeat across graph archive parts: {archive_path}")

    return summary_df
