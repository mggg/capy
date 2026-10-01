"""Read selected graph ZIPs, save per-area metrics, and publish complete-history averages."""

import json
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd
from tqdm import tqdm

from national_pipeline.assign_study_areas.study_area_columns import (
    MembershipColumn,
    StudyAreaColumn,
)
from national_pipeline.build_graphs.archive_inventory import read_graph_selection_summary
from national_pipeline.build_graphs.build_area_graph import GraphStatus
from national_pipeline.build_graphs.graph_archives import read_graph_from_archive
from national_pipeline.data_directories import resolve_separate_output_directory
from national_pipeline.derived_file_paths import build_study_area_label
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import PipelineConfig
from national_pipeline.retrieve_data.prepare_file_requests import build_geography_requests
from national_pipeline.stage_files import stage_file

from .calculate_scores import calculate_graph_metrics
from .metric_types import MetricColumn, MetricSkipReason, UndefinedMetricReason
from .read_graph_inputs import check_graph_population_accounting
from .summarize_years import average_when_all_years_present


def compute_metrics(config: PipelineConfig, repository_root: Path) -> pd.DataFrame:
    """Compute selected metrics from archives without requiring raw or intermediate data files.

    Replace this area type/vintage's tables after reading archive inventories. Each year/level
    table is published separately; averages are removed before computation and written last.
    After an interrupted run, rerun the configuration to recompute the selected scores.

    Args:
        config (PipelineConfig): Graph selections, metrics, comparisons, and input/output folders.
        repository_root (Path): Base for relative configured paths.

    Returns:
        pd.DataFrame: Per-area metric values and explicit undefined reasons across selected archives.

    Raises:
        OSError: An archive cannot be read or a result cannot be written.
        ValueError: Archive selections, graph accounting, or metric inputs are invalid. Unexpected
            computation errors propagate and stop the run rather than becoming undefined results.
    """
    graph_directory = (repository_root / config.graph_archive_directory).resolve()
    input_directories = tuple(
        (repository_root / directory).resolve()
        for directory in (
            config.raw_data_directory,
            config.processed_population_directory,
            config.joined_geography_directory,
            config.study_area_directory,
            config.graph_archive_directory,
        )
    )
    results_root = resolve_separate_output_directory(
        repository_root, config.metric_results_directory, input_directories
    )
    output_directory = results_root / config.study_area_type
    study_area_label = build_study_area_label(config)
    graph_summary_path = output_directory / f"{study_area_label}_graph_summary.parquet"
    averages_path = output_directory / f"{study_area_label}_average_when_all_years_present.parquet"
    output_directory.mkdir(parents=True, exist_ok=True)

    summaries_by_archive = read_selected_graph_summaries(config, graph_directory)
    graph_summary_df = pd.concat(summaries_by_archive.values(), ignore_index=True)

    for previous_table in [
        *output_directory.glob(f"*_{study_area_label}_metrics.parquet"),
        graph_summary_path,
        averages_path,
    ]:
        previous_table.unlink(missing_ok=True)

    metric_tables = []
    expected_years_by_level: dict[GeographyLevel, tuple[int, ...]] = {}

    for archive_path, summary_df in summaries_by_archive.items():
        census_year = int(summary_df[MembershipColumn.CENSUS_YEAR].iloc[0])
        geography_level = GeographyLevel(summary_df[MembershipColumn.GEOGRAPHY_LEVEL].iloc[0])
        output_path = (
            output_directory / f"{census_year}_{geography_level}_{study_area_label}_metrics.parquet"
        )

        try:
            metrics_df = compute_archive_metrics(archive_path, summary_df, config)
        except (BadZipFile, KeyError, json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"{archive_path}: {error}") from error

        save_metric_table(metrics_df, output_path)
        metric_tables.append(metrics_df)
        expected_years_by_level[geography_level] = (
            *expected_years_by_level.get(geography_level, ()),
            census_year,
        )

    metric_values_df = pd.concat(metric_tables, ignore_index=True)
    means_df = average_when_all_years_present(metric_values_df, expected_years_by_level)
    save_metric_table(graph_summary_df, graph_summary_path)
    save_metric_table(means_df, averages_path)

    return metric_values_df


def read_selected_graph_summaries(
    config: PipelineConfig, graph_directory: Path
) -> dict[Path, pd.DataFrame]:
    """Read the selected archive inventories and require the same study areas in every selection.

    Args:
        config (PipelineConfig): Study-area type/vintage and requested years and levels.
        graph_directory (Path): Folder containing graph ZIPs, including numbered parts.

    Returns:
        dict[Path, pd.DataFrame]: Base archive paths and their combined area inventories.

    Raises:
        OSError: A required archive cannot be read.
        ValueError: Inventories are invalid or selected study-area IDs differ.
            ZIP and CSV reader errors propagate.
    """
    summaries_by_archive = {}
    expected_area_ids = None

    for request in build_geography_requests(config):
        if (
            request.census_year not in config.census_geography_years
            or request.geography_level not in config.census_geography_levels
        ):
            continue

        archive_path = graph_directory / (
            f"{config.study_area_type}_{config.study_area_vintage}_"
            f"{request.census_year}_{request.geography_level}.zip"
        )
        summary_df = read_graph_selection_summary(
            archive_path, request.census_year, request.geography_level
        )
        area_ids = set(summary_df[StudyAreaColumn.STUDY_AREA_ID])

        if expected_area_ids is not None and area_ids != expected_area_ids:
            raise ValueError("Selected graph archives do not contain the same study-area IDs")

        expected_area_ids = area_ids
        summaries_by_archive[archive_path] = summary_df

    return summaries_by_archive


def compute_archive_metrics(
    archive_path: Path, graph_summary_df: pd.DataFrame, config: PipelineConfig
) -> pd.DataFrame:
    """Calculate each area's selected metrics and retain outcomes for areas without graphs.

    Args:
        archive_path (Path): Selection's unnumbered base path; parts live in the same directory.
        graph_summary_df (pd.DataFrame): Validated selection inventory with each area's archive name.
        config (PipelineConfig): Selected comparison groups and metric names.

    Returns:
        pd.DataFrame: One row per area/comparison/metric with value or undefined reason, graph
            status, census year, and resolution.

    Raises:
        OSError: An archived graph cannot be read.
        ValueError: Graph identity, population accounting, or metric calculations are invalid.
            JSON and missing-attribute errors propagate to compute_metrics().
    """
    metric_rows = []

    for _, graph_summary in tqdm(
        graph_summary_df.iterrows(),
        total=len(graph_summary_df),
        desc=f"{archive_path.stem} metrics",
        unit="area",
        disable=None,
    ):
        graph_status = GraphStatus(graph_summary[MembershipColumn.STATUS])
        comparison_scores = {
            comparison: dict.fromkeys(config.metric_names, MetricSkipReason.NO_GRAPH)
            for comparison in dict.fromkeys(config.population_comparisons)
        }

        if graph_status == GraphStatus.READY:
            part_path = archive_path.parent / str(graph_summary["archive"])
            graph = read_graph_from_archive(part_path, str(graph_summary["graph_member"]))
            check_graph_population_accounting(graph, graph_summary, config)
            comparison_scores = calculate_graph_metrics(
                graph, config.population_comparisons, config.metric_names
            )

        for comparison, metric_values in comparison_scores.items():
            for metric_name, result in metric_values.items():
                undefined = isinstance(result, (UndefinedMetricReason, MetricSkipReason))
                metric_rows.append(
                    {
                        StudyAreaColumn.STUDY_AREA_ID: graph_summary[StudyAreaColumn.STUDY_AREA_ID],
                        MembershipColumn.CENSUS_YEAR: graph_summary[MembershipColumn.CENSUS_YEAR],
                        MembershipColumn.GEOGRAPHY_LEVEL: graph_summary[
                            MembershipColumn.GEOGRAPHY_LEVEL
                        ],
                        MetricColumn.COMPARISON: comparison.value,
                        MetricColumn.METRIC: metric_name.value,
                        MetricColumn.VALUE: None if undefined else result,
                        MetricColumn.UNDEFINED_REASON: result.value if undefined else None,
                        MetricColumn.GRAPH_STATUS: graph_status.value,
                    }
                )

    metric_values_df = pd.DataFrame(metric_rows)
    metric_values_df[MetricColumn.VALUE] = metric_values_df[MetricColumn.VALUE].astype("Float64")

    return metric_values_df


def save_metric_table(metric_values_df: pd.DataFrame, output_path: Path) -> None:
    """Write a complete Parquet table under a temporary name, then replace its destination."""
    with stage_file(output_path.parent) as temporary_path:
        metric_values_df.to_parquet(temporary_path, index=False)
        temporary_path.replace(output_path)
