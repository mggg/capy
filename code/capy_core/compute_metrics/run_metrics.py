"""Read selected graph ZIPs, save per-area metrics, and publish complete-history averages."""

import json
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd
from tqdm import tqdm

from capy_core.assign_study_areas.study_area_columns import MembershipColumn, StudyAreaColumn
from capy_core.build_graphs.graph_archives import read_graph_from_archive
from capy_core.build_graphs.run_build import GraphStatus
from capy_core.data_directories import resolve_separate_output_directory
from capy_core.geography_types import GeographyLevel
from capy_core.pipeline_config import PipelineConfig
from capy_core.retrieve_data.prepare_file_requests import build_geography_requests
from capy_core.stage_files import stage_file

from .calculate_scores import calculate_graph_metrics
from .metric_types import MetricColumn, MetricSkipReason, UndefinedMetricReason
from .read_graph_inputs import check_graph_population_accounting, read_graph_archive_summary
from .summarize_years import average_when_all_years_present


def compute_metrics(config: PipelineConfig, repository_root: Path) -> pd.DataFrame:
    """Compute selected metrics from archives without requiring raw or intermediate data files.

    Reruns remove this area type/vintage's previous metric tables and means before reading inputs.
    Completed year/level tables are published individually; the complete-history averages are
    written last. A failed run cannot leave an old set of means appearing current.

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
    output_directory = results_root / config.study_area_type / str(config.study_area_vintage)
    output_directory.mkdir(parents=True, exist_ok=True)

    for previous_table in output_directory.glob("*.parquet"):
        previous_table.unlink()

    node_requests = [
        request
        for request in build_geography_requests(config)
        if request.census_year in config.census_geography_years
        and request.geography_level in config.census_geography_levels
    ]
    metric_tables = []
    archive_summaries = []
    expected_area_ids = None
    expected_years_by_level: dict[GeographyLevel, tuple[int, ...]] = {}

    for request in node_requests:
        archive_path = (
            graph_directory
            / f"{config.study_area_type}_{config.study_area_vintage}_{request.census_year}_{request.geography_level}.zip"
        )
        try:
            summary_df = read_graph_archive_summary(
                archive_path, request.census_year, request.geography_level
            )
            area_ids = set(summary_df[StudyAreaColumn.STUDY_AREA_ID])

            if expected_area_ids is not None and area_ids != expected_area_ids:
                raise ValueError("Selected graph archives do not contain the same study-area IDs")

            expected_area_ids = area_ids
            metrics_df = compute_archive_metrics(archive_path, summary_df, config)
        except (BadZipFile, KeyError, json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"{archive_path}: {error}") from error

        output_path = output_directory / f"{request.census_year}_{request.geography_level}.parquet"
        save_metric_table(metrics_df, output_path)
        metric_tables.append(metrics_df)
        archive_summaries.append(summary_df.assign(archive=archive_path.name))
        expected_years_by_level[request.geography_level] = (
            *expected_years_by_level.get(request.geography_level, ()),
            request.census_year,
        )

    metric_values_df = pd.concat(metric_tables, ignore_index=True)
    means_df = average_when_all_years_present(metric_values_df, expected_years_by_level)
    save_metric_table(
        pd.concat(archive_summaries, ignore_index=True), output_directory / "graph_outcomes.parquet"
    )
    save_metric_table(means_df, output_directory / "average_when_all_years_present.parquet")

    return metric_values_df


def compute_archive_metrics(
    archive_path: Path, graph_summary_df: pd.DataFrame, config: PipelineConfig
) -> pd.DataFrame:
    """Calculate each area's selected metrics and retain outcomes for areas without graphs.

    Args:
        archive_path (Path): ZIP whose inventory has passed read_graph_archive_summary().
        graph_summary_df (pd.DataFrame): One archive-summary row per area.
        config (PipelineConfig): Selected comparison groups and metric names.

    Returns:
        pd.DataFrame: One row per area/comparison/metric with value or undefined reason, graph
            status, census year, and resolution. A graph loads once for both comparisons.

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
            graph = read_graph_from_archive(archive_path, str(graph_summary["graph_member"]))
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
