"""Prepare saved national comparison inputs without rendering figures."""

from pathlib import Path

import numpy as np
import pandas as pd
from experiments.grid_configurations.grid_reference_scores import build_grid_reference_scores
from national_pipeline.assign_study_areas.study_area_columns import (
    MembershipColumn,
    StudyAreaColumn,
)
from national_pipeline.compute_metrics.metric_types import (
    MetricColumn,
    MetricName,
    PopulationComparison,
)
from national_pipeline.geography_types import GeographyLevel, MetroCode, StudyAreaType
from national_pipeline.pipeline_config import PipelineConfig

from national_figures.prepare_national_results import (
    check_figure_score_selection,
    read_national_figure_inputs,
)

COMPARISON_METRICS = (
    MetricName.DISSIMILARITY,
    MetricName.ENTROPY_INDEX,
    MetricName.RELATIVE_DIVERSITY,
    MetricName.ASPATIAL_CAPY,
    MetricName.SPATIAL_DISSIMILARITY,
    MetricName.SPATIAL_ENTROPY_INDEX,
    MetricName.SPATIAL_RELATIVE_DIVERSITY,
    MetricName.CAPY,
    MetricName.MORAN_WITH_SELF,
    MetricName.MORAN_ROW_STANDARDIZED,
)

GRID_COMPARISONS = (PopulationComparison.WHITE_BLACK, PopulationComparison.WHITE_POC)


TOP_10_METRO_CODES = (
    MetroCode.NEW_YORK,
    MetroCode.LOS_ANGELES,
    MetroCode.CHICAGO,
    MetroCode.DALLAS,
    MetroCode.HOUSTON,
    MetroCode.WASHINGTON,
    MetroCode.PHILADELPHIA,
    MetroCode.MIAMI,
    MetroCode.ATLANTA,
    MetroCode.BOSTON,
)


def attach_tract_score_populations(
    metrics_df: pd.DataFrame,
    definitions_df: pd.DataFrame,
    graph_summary_df: pd.DataFrame,
) -> pd.DataFrame:
    """Join tract scores to their actual retained populations and study-area names.

    Args:
        metrics_df (pd.DataFrame): Long pipeline score rows, including undefined outcomes.
        definitions_df (pd.DataFrame): Unique study-area IDs, names, and metro codes.
        graph_summary_df (pd.DataFrame): Graph accounting with retained White, Black, and POC counts.

    Returns:
        pd.DataFrame: One row per tract area/year/comparison with oriented Black or POC share.
            Undefined metrics remain null. No population cutoff or named-area exclusion is applied.

    Raises:
        ValueError: Identities repeat, accounting or definitions are missing.
    """
    area_year_columns = [StudyAreaColumn.STUDY_AREA_ID, MembershipColumn.CENSUS_YEAR]
    selected_df = metrics_df.loc[
        metrics_df[MembershipColumn.GEOGRAPHY_LEVEL].eq(GeographyLevel.TRACT)
        & metrics_df[MetricColumn.METRIC].isin(COMPARISON_METRICS)
    ]

    scores_df = selected_df.pivot(
        index=[*area_year_columns, MetricColumn.COMPARISON],
        columns=MetricColumn.METRIC,
        values=MetricColumn.VALUE,
    ).reset_index()

    counts_df = graph_summary_df.loc[
        graph_summary_df[MembershipColumn.GEOGRAPHY_LEVEL].eq(GeographyLevel.TRACT)
    ]
    scores_df = scores_df.merge(
        counts_df[[*area_year_columns, "retained_WHITE", "retained_BLACK", "retained_POC"]],
        on=area_year_columns,
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    if not scores_df["_merge"].eq("both").all():
        raise ValueError("Tract scores lack graph population accounting")

    scores_df = scores_df.drop(columns="_merge").merge(
        definitions_df[
            [StudyAreaColumn.STUDY_AREA_ID, StudyAreaColumn.NAME, StudyAreaColumn.METRO_CODE]
        ],
        on=StudyAreaColumn.STUDY_AREA_ID,
        how="left",
        validate="many_to_one",
    )

    if scores_df[StudyAreaColumn.METRO_CODE].isna().any():
        raise ValueError("Tract scores lack a study-area definition")

    second_group_counts = np.where(
        scores_df[MetricColumn.COMPARISON].eq(PopulationComparison.WHITE_BLACK),
        scores_df.retained_BLACK,
        scores_df.retained_POC,
    )
    scores_df["group_share"] = second_group_counts / (
        second_group_counts + scores_df.retained_WHITE
    )

    return scores_df


def read_tract_score_inputs(
    config: PipelineConfig,
    repository_root: Path,
    years: list[int],
    comparisons: tuple[PopulationComparison, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read tract scores with retained populations and the top-ten metro definitions.

    Args:
        config (PipelineConfig): CBSA or maximum-city definitions and requested comparisons.
        repository_root (Path): Base for configured input paths.
        years (list[int]): Census years to read.
        comparisons (tuple[PopulationComparison, ...]): Configured comparisons for these images.

    Returns:
        tuple[pd.DataFrame, pd.DataFrame]: Wide scores and selected-area definitions in the fixed
            2020 metro order.

    Raises:
        OSError: A selected input cannot be read.
        ValueError: Required selections, score identities, or accounting are absent.
    """
    if config.study_area_type not in (StudyAreaType.CBSA, StudyAreaType.MAX_CITY):
        raise ValueError("Tract score comparisons support CBSAs and maximum cities")

    if GeographyLevel.TRACT not in config.census_geography_levels or not years or not comparisons:
        raise ValueError("Tract score comparisons require selected tract years")

    selected_metrics = tuple(
        metric for metric in COMPARISON_METRICS if metric in config.metric_names
    )

    if not selected_metrics:
        raise ValueError("No configured metrics match the tract score comparisons")

    history_years_by_selection = {
        (comparison, GeographyLevel.TRACT): years for comparison in comparisons
    }
    metrics_df, definitions_df, graph_summary_df = read_national_figure_inputs(
        config, repository_root, history_years_by_selection
    )

    metrics_df = metrics_df.loc[
        metrics_df[MetricColumn.COMPARISON].isin(comparisons)
        & metrics_df[MembershipColumn.CENSUS_YEAR].isin(years)
        & metrics_df[MetricColumn.METRIC].isin(selected_metrics)
    ]
    selected_graphs_df = graph_summary_df.loc[
        graph_summary_df[MembershipColumn.GEOGRAPHY_LEVEL].eq(GeographyLevel.TRACT)
        & graph_summary_df[MembershipColumn.CENSUS_YEAR].isin(years)
    ]

    if metrics_df.empty or selected_graphs_df.empty:
        raise ValueError(
            "No selected tract observations are available for the tract score comparisons"
        )

    tract_selections_df = pd.DataFrame(
        list(history_years_by_selection),
        columns=pd.Index([MetricColumn.COMPARISON, MembershipColumn.GEOGRAPHY_LEVEL]),
    )
    check_figure_score_selection(
        metrics_df, selected_graphs_df, tract_selections_df, selected_metrics
    )

    scores_df = attach_tract_score_populations(metrics_df, definitions_df, selected_graphs_df)

    top_10_metros_df = definitions_df.loc[
        definitions_df[StudyAreaColumn.METRO_CODE].isin(TOP_10_METRO_CODES)
    ].copy()
    metro_order = {metro_code: rank for rank, metro_code in enumerate(TOP_10_METRO_CODES)}
    top_10_metros_df = top_10_metros_df.sort_values(
        StudyAreaColumn.METRO_CODE, key=lambda codes: codes.map(metro_order)
    )

    return scores_df, top_10_metros_df


def prepare_grid_vs_national_scores(
    config: PipelineConfig, repository_root: Path, data_directory: Path
) -> None:
    """Save 2020 national scores, grid references, and top-ten definitions for comparisons.

    Args:
        config (PipelineConfig): Study areas and selected comparisons, including 2020 tracts.
        repository_root (Path): Base for configured input paths.
        data_directory (Path): Destination for tract_scores, reference_scores, and top_10_metros.

    Raises:
        OSError: Reading inputs or saving prepared tables fails.
        ValueError: Required scores, accounting, or 2020 selection is absent.
    """
    if 2020 not in config.census_geography_years:
        raise ValueError("Grid-versus-national scores require 2020 in the configured Census years")

    comparisons = tuple(
        comparison for comparison in GRID_COMPARISONS if comparison in config.population_comparisons
    )

    scores_df, top_10_metros_df = read_tract_score_inputs(
        config, repository_root, [2020], comparisons
    )

    references_df = build_grid_reference_scores()

    data_directory.mkdir(parents=True, exist_ok=True)
    scores_df.to_parquet(data_directory / "tract_scores.parquet", index=False)
    references_df.to_parquet(data_directory / "reference_scores.parquet", index=False)
    top_10_metros_df.to_parquet(data_directory / "top_10_metros.parquet", index=False)
