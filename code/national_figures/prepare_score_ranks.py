"""Prepare population-selected score ranks and correlations."""

from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from national_pipeline.assign_study_areas.study_area_columns import (
    MembershipColumn,
    StudyAreaColumn,
)
from national_pipeline.compute_metrics.metric_types import (
    MetricColumn,
    MetricName,
)
from national_pipeline.pipeline_config import PipelineConfig

from national_figures.prepare_national_results import (
    PRIMARY_METRICS,
    check_figure_score_selection,
    read_national_figure_inputs,
    select_figure_years_by_selection,
)


def select_population_rank_sample(
    scores_df: pd.DataFrame,
    graph_summary_df: pd.DataFrame,
    metric_names: tuple[MetricName, ...] = PRIMARY_METRICS,
) -> pd.DataFrame:
    """Rank the selected scores ascending within the 100 largest complete populations for one selection.

    Ties receive average ranks. Population ties are broken by area ID. Selection precedes score
    ranking, so ranks describe the same complete metro sample in every pairwise panel.

    Args:
        scores_df (pd.DataFrame): Primary metric rows for one year, level, and comparison.
        graph_summary_df (pd.DataFrame): Graph accounting with retained total population.
        metric_names (tuple[MetricName, ...]): Scores defining the complete sample; defaults to
            the three primary metrics.

    Returns:
        pd.DataFrame: Selected scores, population, and suffixed rank columns indexed by area ID.

    Raises:
        ValueError: Score or accounting identities repeat, or population accounting is missing.
    """
    values_df = scores_df.pivot(
        index=StudyAreaColumn.STUDY_AREA_ID, columns=MetricColumn.METRIC, values=MetricColumn.VALUE
    )
    values_df = values_df.reindex(columns=metric_names).replace([np.inf, -np.inf], np.nan).dropna()
    values_df = values_df.join(
        graph_summary_df.set_index(StudyAreaColumn.STUDY_AREA_ID)["retained_TOTPOP"],
        validate="one_to_one",
    )

    if bool(values_df["retained_TOTPOP"].isna().any()):
        raise ValueError("Rank sample lacks retained population accounting")

    values_df = (
        values_df.reset_index()
        .sort_values(["retained_TOTPOP", StudyAreaColumn.STUDY_AREA_ID], ascending=[False, True])
        .head(100)
    )
    values_df = values_df.set_index(StudyAreaColumn.STUDY_AREA_ID)

    return values_df.join(
        values_df[list(metric_names)].rank(ascending=True, method="average").add_suffix("_rank")
    )


def prepare_score_rank_data(
    config: PipelineConfig, repository_root: Path, data_directory: Path, table_directory: Path
) -> None:
    """Save population-selected ranks and correlations for each configured year/level/comparison.

    Each sample contains the 100 largest retained populations with finite values for every
    selected primary score. Definition population must exceed 100,000. At least two primary
    metrics are needed for pairwise comparisons.

    Args:
        config (PipelineConfig): Selected study areas, years, levels, comparisons, and metrics.
        repository_root (Path): Base for configured relative input paths.
        data_directory (Path): Destination for prepared rank_rows.parquet plotting inputs.
        table_directory (Path): Destination for the finished rank_correlations.parquet table.

    Raises:
        OSError: Reading inputs or saving tables fails.
        ValueError: Selected scores are missing, fewer than two primary metrics are selected,
            or a selection has no complete score sample.
    """
    metric_names = tuple(metric for metric in PRIMARY_METRICS if metric in config.metric_names)
    if len(metric_names) < 2:
        raise ValueError("Score rank comparisons need at least two selected primary metrics")

    years_by_selection = select_figure_years_by_selection(config)
    metrics_df, definitions_df, graph_summary_df = read_national_figure_inputs(
        config, repository_root, years_by_selection
    )
    eligible_ids = definitions_df.loc[
        definitions_df[StudyAreaColumn.DEFINITION_POPULATION].gt(100000),
        StudyAreaColumn.STUDY_AREA_ID,
    ]
    comparison_metrics = [
        metric
        for metric in (MetricName.CAPY, MetricName.DISSIMILARITY, MetricName.MORAN_ROW_STANDARDIZED)
        if metric in metric_names
    ]
    selection_columns = [
        MembershipColumn.CENSUS_YEAR,
        MembershipColumn.GEOGRAPHY_LEVEL,
        MetricColumn.COMPARISON,
    ]
    rank_tables = []
    correlation_rows = []

    selections = [
        (year, level, comparison)
        for (comparison, level), years in years_by_selection.items()
        for year in years
    ]
    for year, level, comparison in selections:
        selection_graphs_df = graph_summary_df.loc[
            graph_summary_df[MembershipColumn.CENSUS_YEAR].eq(year)
            & graph_summary_df[MembershipColumn.GEOGRAPHY_LEVEL].eq(level)
        ]
        if selection_graphs_df.empty:
            raise ValueError(f"No graph summary for {year} {level}")

        selection_df = metrics_df.loc[
            metrics_df[MembershipColumn.CENSUS_YEAR].eq(year)
            & metrics_df[MembershipColumn.GEOGRAPHY_LEVEL].eq(level)
            & metrics_df[MetricColumn.COMPARISON].eq(comparison)
            & metrics_df[MetricColumn.METRIC].isin(metric_names)
        ]
        score_selections_df = pd.DataFrame(
            {MetricColumn.COMPARISON: [comparison], MembershipColumn.GEOGRAPHY_LEVEL: [level]}
        )
        check_figure_score_selection(
            selection_df, selection_graphs_df, score_selections_df, metric_names
        )
        selection_df = selection_df.loc[
            selection_df[StudyAreaColumn.STUDY_AREA_ID].isin(eligible_ids)
        ]
        ranks_df = select_population_rank_sample(selection_df, selection_graphs_df, metric_names)
        if ranks_df.empty:
            raise ValueError(f"No complete score sample for {year} {level} {comparison} ranks")

        selection = dict(zip(selection_columns, (year, level, comparison)))
        rank_tables.append(ranks_df.reset_index().assign(**selection))
        for x_metric, y_metric in combinations(comparison_metrics, 2):
            correlation_rows.append(
                {
                    **selection,
                    "x_metric": x_metric,
                    "y_metric": y_metric,
                    "area_count": len(ranks_df),
                    "spearman": pd.DataFrame(ranks_df[[x_metric, y_metric]])
                    .corr(method="spearman")
                    .iloc[0, 1],
                }
            )

    ranks_df = pd.concat(rank_tables, ignore_index=True)
    correlations_df = pd.DataFrame(correlation_rows)
    data_directory.mkdir(parents=True, exist_ok=True)
    ranks_df.to_parquet(data_directory / "rank_rows.parquet", index=False)

    table_directory.mkdir(parents=True, exist_ok=True)
    correlations_df.to_parquet(table_directory / "rank_correlations.parquet", index=False)
