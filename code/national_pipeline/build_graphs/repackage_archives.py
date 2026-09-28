"""Convert saved national graph archives while preserving completed graph and metric work."""

from pathlib import Path

import pandas as pd
from tqdm import tqdm

from national_pipeline.pipeline_config import PipelineConfig
from national_pipeline.retrieve_data.prepare_file_requests import build_geography_requests
from national_pipeline.stage_files import stage_file

from .archive_inventory import read_graph_selection_summary
from .archive_parts import publish_graph_archive_parts


def repackage_graph_archives(config: PipelineConfig, repository_root: Path) -> None:
    """Replace available legacy ZIPs with checked parts and write a run summary if all selections exist.

    Missing selections are left for build-graphs to finish. Repeating this command reuses complete
    parts. The legacy source is removed only after all replacements are verified and published.
    If interrupted earlier, the legacy source remains authoritative. No graphs are recalculated.

    Args:
        config (PipelineConfig): Graph folder, study-area type/vintage, and node selections.
        repository_root (Path): Base for configured relative paths.

    Raises:
        OSError: Reading, publishing, or deleting the superseded source fails.
        ValueError: An archive is inconsistent, contents change, or a part exceeds the size limit.
            ZIP errors also propagate. Published parts can be reused after an interrupted run.
    """
    graph_directory = (repository_root / config.graph_archive_directory).resolve()
    archive_prefix = f"{config.study_area_type}_{config.study_area_vintage}"
    summary_path = graph_directory / f"{archive_prefix}_summary.parquet"
    summary_path.unlink(missing_ok=True)
    summaries = []
    all_selections_present = True

    for request in build_geography_requests(config):
        if (
            request.census_year not in config.census_geography_years
            or request.geography_level not in config.census_geography_levels
        ):
            continue

        archive_path = graph_directory / (
            f"{archive_prefix}_{request.census_year}_{request.geography_level}.zip"
        )

        if archive_path.exists():
            read_graph_selection_summary(archive_path, request.census_year, request.geography_level)
            summary_df = publish_graph_archive_parts(archive_path, archive_path)
            archive_path.unlink()
            tqdm.write(
                f"Repackaged {archive_path.name} into {summary_df.archive.nunique()} part(s)"
            )
        else:
            try:
                summary_df = read_graph_selection_summary(
                    archive_path, request.census_year, request.geography_level
                )
            except FileNotFoundError:
                all_selections_present = False
                tqdm.write(f"Not yet built: {archive_path.stem}")
                continue

        summaries.append(summary_df)

    if all_selections_present:
        with stage_file(graph_directory) as temporary_path:
            pd.concat(summaries, ignore_index=True).to_parquet(temporary_path, index=False)
            temporary_path.replace(summary_path)
