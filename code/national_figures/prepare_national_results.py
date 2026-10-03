"""Prepare national figure cohorts, comparisons, and publication tables from pipeline results."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from national_pipeline.assign_study_areas.study_area_columns import (
    MembershipColumn,
    StudyAreaColumn,
)
from national_pipeline.compute_metrics.metric_types import (
    MetricColumn,
    MetricName,
    PopulationComparison,
)
from national_pipeline.derived_file_paths import build_study_area_label
from national_pipeline.geography_types import GeographyLevel, StudyAreaType
from national_pipeline.pipeline_config import PipelineConfig
from national_pipeline.retrieve_data.prepare_file_requests import build_geography_requests

PRIMARY_METRICS = (MetricName.MORAN_ROW_STANDARDIZED, MetricName.DISSIMILARITY, MetricName.CAPY)
HISTORY_METRICS = (
    *PRIMARY_METRICS,
    MetricName.ENTROPY_INDEX,
    MetricName.RELATIVE_DIVERSITY,
    MetricName.ASPATIAL_CAPY,
    MetricName.SPATIAL_DISSIMILARITY,
    MetricName.SPATIAL_ENTROPY_INDEX,
    MetricName.SPATIAL_RELATIVE_DIVERSITY,
    MetricName.MORAN_WITH_SELF,
)

# Two-node 1980 BNA graphs force Moran's I to -1, so we exclude their complete tract histories.
TWO_NODE_1980_CBSA_IDS = frozenset(
    {"cbsa_25940", "cbsa_29420", "cbsa_35100", "cbsa_39150", "cbsa_39460"}
)
IDENTITY_COLUMNS = [
    StudyAreaColumn.STUDY_AREA_ID,
    MembershipColumn.CENSUS_YEAR,
    MembershipColumn.GEOGRAPHY_LEVEL,
]
# Image sets to prepare when their comparison and geography are selected in the run config.
HISTORY_SELECTIONS = (
    (PopulationComparison.WHITE_BLACK, GeographyLevel.TRACT),
    (PopulationComparison.WHITE_BLACK, GeographyLevel.BLOCK_GROUP),
    (PopulationComparison.WHITE_BLACK, GeographyLevel.BLOCK),
    (PopulationComparison.WHITE_POC, GeographyLevel.TRACT),
    (PopulationComparison.WHITE_POC, GeographyLevel.BLOCK_GROUP),
    (PopulationComparison.WHITE_POC, GeographyLevel.BLOCK),
)


def select_history_years(
    config: PipelineConfig,
) -> dict[tuple[PopulationComparison, GeographyLevel], list[int]]:
    """Select configured image sets and their supported Census years.

    Args:
        config (PipelineConfig): Requested comparisons, node levels, and Census years.

    Returns:
        dict[tuple[PopulationComparison, GeographyLevel], list[int]]: Required years per image set,
            using the pipeline's source coverage rules to omit unavailable 1980 resolutions.

    Raises:
        ValueError: No supported configured selections match the history image sets.
    """
    geography_requests = build_geography_requests(config)
    years_by_selection = {}

    for comparison, level in HISTORY_SELECTIONS:
        if (
            comparison not in config.population_comparisons
            or level not in config.census_geography_levels
        ):
            continue

        years = [
            request.census_year
            for request in geography_requests
            if request.geography_level == level
            and request.census_year in config.census_geography_years
        ]

        if years:
            years_by_selection[comparison, level] = years

    if not years_by_selection:
        raise ValueError("No configured selections match the national history image sets")

    return years_by_selection


def select_figure_years_by_selection(
    config: PipelineConfig,
) -> dict[tuple[PopulationComparison, GeographyLevel], list[int]]:
    """Resolve configured population comparisons and available graph years at each level.

    Source coverage omits unavailable combinations such as 1980 blocks and block groups.
    Counties, tracts, block groups, and blocks are supported graph units.

    Args:
        config (PipelineConfig): Requested years, geography levels, and population comparisons.

    Returns:
        dict[tuple[PopulationComparison, GeographyLevel], list[int]]: Supported years, sorted
            within each configured comparison and level.

    Raises:
        ValueError: The configuration selects no supported graph geography.
    """
    graph_levels = (
        GeographyLevel.COUNTY,
        GeographyLevel.TRACT,
        GeographyLevel.BLOCK_GROUP,
        GeographyLevel.BLOCK,
    )
    years_by_level: dict[GeographyLevel, set[int]] = {}

    for request in build_geography_requests(config):
        if (
            request.geography_level not in graph_levels
            or request.geography_level not in config.census_geography_levels
            or request.census_year not in config.census_geography_years
        ):
            continue

        years_by_level.setdefault(request.geography_level, set()).add(request.census_year)

    if not years_by_level:
        raise ValueError("No configured years and levels have supported graph geography")

    return {
        (comparison, level): sorted(years)
        for comparison in config.population_comparisons
        for level, years in years_by_level.items()
    }


def read_national_figure_inputs(
    config: PipelineConfig,
    repository_root: Path,
    history_years_by_selection: dict[tuple[PopulationComparison, GeographyLevel], list[int]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read the selected image sets' metric tables, area definitions, and graph summaries.

    Args:
        config (PipelineConfig): Study-area choice and input directories.
        repository_root (Path): Base for configured relative paths.
        history_years_by_selection (dict): Supported years per selected comparison and level.

    Returns:
        tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]: Metric rows, study-area attributes,
            and graph summaries. Each selected image set's year/level tables are required.

    Raises:
        OSError: An input is missing or unreadable.
        ValueError: No supported metric tables can be concatenated.
    """
    area_folder = Path(config.study_area_type) / str(config.study_area_vintage)
    metric_directory = repository_root / config.metric_results_directory / config.study_area_type
    study_area_label = build_study_area_label(config)

    definitions_df = gpd.read_parquet(
        repository_root / config.study_area_directory / area_folder / "definitions.parquet"
    ).drop(columns="geometry")

    requested_year_levels = {
        (year, level) for (_, level), years in history_years_by_selection.items() for year in years
    }

    metric_tables = []
    for year, level in sorted(requested_year_levels):
        metric_path = metric_directory / f"{year}_{level}_{study_area_label}_metrics.parquet"
        metric_tables.append(pd.read_parquet(metric_path))

    metrics_df = pd.concat(metric_tables, ignore_index=True)
    graph_summary_df = pd.read_parquet(
        metric_directory / f"{study_area_label}_graph_summary.parquet"
    )

    return metrics_df, definitions_df, graph_summary_df


def prepare_national_figure_data(
    config: PipelineConfig, repository_root: Path, data_directory: Path
) -> None:
    """Save the national figure inputs without rendering images.

    Histories require finite scores throughout the period and definition population above 100,000.
    Scores come from the completed pipeline metric tables. Image sets use the configured years,
    geography levels, comparisons, and history metrics; unavailable 1980 resolutions are omitted.

    Args:
        config (PipelineConfig): Study areas, years, levels, comparisons, and available metrics.
        repository_root (Path): Base for configured pipeline input folders.
        data_directory (Path): Destination for selected rows and publication tables.

    Raises:
        OSError: An input cannot be read or an output cannot be written.
        ValueError: Required selections or input identities are invalid.
    """
    history_years_by_selection = select_history_years(config)
    selected_metrics = tuple(metric for metric in HISTORY_METRICS if metric in config.metric_names)
    history_selections_df = pd.DataFrame(
        list(history_years_by_selection),
        columns=pd.Index([MetricColumn.COMPARISON, MembershipColumn.GEOGRAPHY_LEVEL]),
    )

    metrics_df, definitions_df, graph_summary_df = read_national_figure_inputs(
        config, repository_root, history_years_by_selection
    )
    eligible_areas_df = definitions_df.loc[
        definitions_df[StudyAreaColumn.DEFINITION_POPULATION].gt(100000)
    ]
    eligible_areas_df = eligible_areas_df.sort_values(
        [StudyAreaColumn.DEFINITION_POPULATION, StudyAreaColumn.STUDY_AREA_ID],
        ascending=[False, True],
    )
    top_10_metros_df = eligible_areas_df.head(10)

    history_levels = history_selections_df[MembershipColumn.GEOGRAPHY_LEVEL]
    selected_graph_summary_df = graph_summary_df.loc[
        graph_summary_df[StudyAreaColumn.STUDY_AREA_ID].isin(
            eligible_areas_df[StudyAreaColumn.STUDY_AREA_ID]
        )
        & graph_summary_df[MembershipColumn.GEOGRAPHY_LEVEL].isin(history_levels)
        & graph_summary_df[MembershipColumn.CENSUS_YEAR].isin(config.census_geography_years)
    ]

    selected_metrics_df = metrics_df.merge(
        history_selections_df, on=[MetricColumn.COMPARISON, MembershipColumn.GEOGRAPHY_LEVEL]
    )
    national_scores_df = selected_metrics_df.loc[
        selected_metrics_df[MetricColumn.METRIC].isin(selected_metrics)
        & selected_metrics_df[StudyAreaColumn.STUDY_AREA_ID].isin(
            eligible_areas_df[StudyAreaColumn.STUDY_AREA_ID]
        )
        & selected_metrics_df[MembershipColumn.CENSUS_YEAR].isin(config.census_geography_years)
    ]

    check_figure_score_selection(
        national_scores_df, selected_graph_summary_df, history_selections_df, selected_metrics
    )
    histories_df = select_score_histories(
        national_scores_df, history_years_by_selection, selected_metrics, config
    )

    data_directory.mkdir(parents=True, exist_ok=True)
    national_scores_df.to_parquet(data_directory / "national_score_rows.parquet", index=False)
    eligible_areas_df.to_parquet(data_directory / "eligible_areas.parquet", index=False)
    top_10_metros_df.to_parquet(data_directory / "top_10_metros.parquet", index=False)
    histories_df.to_parquet(data_directory / "trajectory_rows.parquet", index=False)


def check_figure_score_selection(
    scores_df: pd.DataFrame,
    graph_summary_df: pd.DataFrame,
    history_selections_df: pd.DataFrame,
    selected_metrics: tuple[MetricName, ...],
) -> None:
    """Require each configured score for every graph/comparison in the image sets.

    Args:
        scores_df (pd.DataFrame): Selected pipeline scores, including undefined results.
        graph_summary_df (pd.DataFrame): Selected area/year/level graph accounting.
        history_selections_df (pd.DataFrame): Selected comparison/level pairs, one row per image set.
        selected_metrics (tuple[MetricName, ...]): Scores requested for each image set.

    Raises:
        ValueError: Identities repeat, are missing, or disagree with the selected graph summary.
    """
    identities = [*IDENTITY_COLUMNS, MetricColumn.COMPARISON, MetricColumn.METRIC]
    expected_df = (
        graph_summary_df[IDENTITY_COLUMNS]
        .merge(history_selections_df, on=MembershipColumn.GEOGRAPHY_LEVEL)
        .merge(pd.DataFrame({MetricColumn.METRIC: selected_metrics}), how="cross")
    )

    if (
        scores_df[identities].isna().to_numpy().any()
        or scores_df.duplicated(identities).any()
        or set(map(tuple, scores_df[identities].to_numpy()))
        != set(map(tuple, expected_df[identities].to_numpy()))
    ):
        raise ValueError(
            "Pipeline score rows are missing or disagree with the selected graph summaries; "
            "run compute-metrics with the configured metrics and population comparisons"
        )


def select_score_histories(
    scores_df: pd.DataFrame,
    history_years_by_selection: dict[tuple[PopulationComparison, GeographyLevel], list[int]],
    selected_metrics: tuple[MetricName, ...],
    config: PipelineConfig,
) -> pd.DataFrame:
    """Select complete histories for each image set, applying historical coverage exclusions.

    Args:
        scores_df (pd.DataFrame): Pipeline scores for eligible areas.
        history_years_by_selection (dict): Required years per selected comparison and level.
        selected_metrics (tuple[MetricName, ...]): Scores requested for each image set.
        config (PipelineConfig): Study-area type and vintage governing historical exclusions.

    Returns:
        pd.DataFrame: Complete cohorts in selection/metric order, with each cohort sorted by area
            and year.

    Raises:
        ValueError: Area/year identities repeat, a selected cohort is empty, or no scores
            are selected.
    """
    cohort_tables = []

    for (comparison, level), years in history_years_by_selection.items():
        selected_df = scores_df.loc[
            scores_df[MetricColumn.COMPARISON].eq(comparison)
            & scores_df[MembershipColumn.GEOGRAPHY_LEVEL].eq(level)
        ]

        if (
            config.study_area_type == StudyAreaType.CBSA
            and config.study_area_vintage == 2020
            and 1980 in years
            and comparison == PopulationComparison.WHITE_BLACK
            and level == GeographyLevel.TRACT
        ):
            selected_df = selected_df.loc[
                ~selected_df[StudyAreaColumn.STUDY_AREA_ID].isin(TWO_NODE_1980_CBSA_IDS)
            ]

        for metric in selected_metrics:
            complete_df = select_complete_histories(
                selected_df.loc[selected_df[MetricColumn.METRIC].eq(metric)], years
            )

            if complete_df.empty:
                raise ValueError(f"No complete score histories for {comparison} {level} {metric}")

            cohort_tables.append(complete_df)

    if not cohort_tables:
        raise ValueError("No configured scores match the national history image sets")

    return pd.concat(cohort_tables, ignore_index=True)


def select_complete_histories(scores_df: pd.DataFrame, years: list[int]) -> pd.DataFrame:
    """Keep areas with one finite score in every requested year, preserving a fixed cohort.

    Args:
        scores_df (pd.DataFrame): One comparison, resolution, and metric, with area/year/value.
        years (list[int]): Years required for every retained area.

    Returns:
        pd.DataFrame: Requested rows for complete areas, sorted by identity and year.

    Raises:
        ValueError: Area/year rows repeat, so a trajectory would be ambiguous.
    """
    selected_df = scores_df.loc[scores_df[MembershipColumn.CENSUS_YEAR].isin(years)]

    if selected_df.duplicated([StudyAreaColumn.STUDY_AREA_ID, MembershipColumn.CENSUS_YEAR]).any():
        raise ValueError("A trajectory needs one score per area and year")

    finite_df = selected_df.loc[np.isfinite(selected_df[MetricColumn.VALUE].astype(float))]
    year_counts = finite_df.groupby(StudyAreaColumn.STUDY_AREA_ID)[
        MembershipColumn.CENSUS_YEAR
    ].nunique()
    complete_ids = year_counts.index[year_counts.eq(len(set(years)))]

    return finite_df.loc[finite_df[StudyAreaColumn.STUDY_AREA_ID].isin(complete_ids)].sort_values(
        [StudyAreaColumn.STUDY_AREA_ID, MembershipColumn.CENSUS_YEAR]
    )
