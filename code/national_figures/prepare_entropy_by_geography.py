"""Prepare complete White–Black entropy histories at selected geographic resolutions."""

from pathlib import Path

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
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import PipelineConfig
from national_pipeline.retrieve_data.prepare_file_requests import build_geography_requests

from national_figures.prepare_national_results import (
    read_national_figure_inputs,
    select_complete_histories,
)

ENTROPY_LEVELS = (GeographyLevel.TRACT, GeographyLevel.BLOCK_GROUP, GeographyLevel.BLOCK)


def select_entropy_histories(
    metrics_df: pd.DataFrame,
    definitions_df: pd.DataFrame,
    years_by_level: dict[GeographyLevel, list[int]],
) -> pd.DataFrame:
    """Keep finite White–Black entropy histories above 100,000 definition population.

    Each geographic level has its own fixed complete cohort over its supported selected years.

    Args:
        metrics_df (pd.DataFrame): Long pipeline scores across years, levels, and comparisons.
        definitions_df (pd.DataFrame): Study-area identities and definition population.
        years_by_level (dict[GeographyLevel, list[int]]): Supported selected years per level.

    Returns:
        pd.DataFrame: Complete histories, sorted by identity and year within each level.

    Raises:
        ValueError: A level has repeated observations or no complete entropy histories.
    """
    eligible_ids = definitions_df.loc[
        definitions_df[StudyAreaColumn.DEFINITION_POPULATION].gt(100000),
        StudyAreaColumn.STUDY_AREA_ID,
    ]
    selected_df = metrics_df.loc[
        metrics_df[MetricColumn.METRIC].eq(MetricName.ENTROPY_INDEX)
        & metrics_df[MetricColumn.COMPARISON].eq(PopulationComparison.WHITE_BLACK)
        & metrics_df[StudyAreaColumn.STUDY_AREA_ID].isin(eligible_ids)
    ]
    history_tables = []
    for level, years in years_by_level.items():
        level_df = selected_df.loc[selected_df[MembershipColumn.GEOGRAPHY_LEVEL].eq(level)]
        histories_df = select_complete_histories(level_df, years)
        if histories_df.empty:
            raise ValueError(f"No complete White–Black entropy histories for {level}")
        history_tables.append(histories_df)
    return pd.concat(history_tables, ignore_index=True)


def prepare_entropy_data(
    config: PipelineConfig, repository_root: Path, data_directory: Path
) -> None:
    """Save complete entropy cohorts and population-ranked top-ten study-area definitions.

    Only configured resolutions and their supported Census years are read.

    Args:
        config (PipelineConfig): Study areas, Census years/levels, and upstream input folders.
        repository_root (Path): Base for configured relative paths.
        data_directory (Path): Destination for entropy_histories and top_10_metros Parquets.

    Raises:
        OSError: An input cannot be read or an output cannot be written.
        ValueError: Required selections are absent or a top-ten area lacks a complete history.
    """
    if (
        PopulationComparison.WHITE_BLACK not in config.population_comparisons
        or MetricName.ENTROPY_INDEX not in config.metric_names
    ):
        raise ValueError("Entropy histories require configured White–Black entropy scores")
    geography_requests = build_geography_requests(config)
    years_by_level = {}
    for level in ENTROPY_LEVELS:
        years = sorted(
            {
                request.census_year
                for request in geography_requests
                if request.geography_level == level
                and level in config.census_geography_levels
                and request.census_year in config.census_geography_years
            }
        )
        if years:
            years_by_level[level] = years
    if not years_by_level:
        raise ValueError("No configured resolutions match the entropy history image sets")

    selections = {
        (PopulationComparison.WHITE_BLACK, level): years for level, years in years_by_level.items()
    }
    metrics_df, definitions_df, _ = read_national_figure_inputs(config, repository_root, selections)
    histories_df = select_entropy_histories(metrics_df, definitions_df, years_by_level)
    top_10_metros_df = (
        definitions_df.loc[definitions_df[StudyAreaColumn.DEFINITION_POPULATION].gt(100000)]
        .sort_values(
            [StudyAreaColumn.DEFINITION_POPULATION, StudyAreaColumn.STUDY_AREA_ID],
            ascending=[False, True],
        )
        .head(10)
    )
    for level, level_df in histories_df.groupby(MembershipColumn.GEOGRAPHY_LEVEL):
        missing_metros = set(top_10_metros_df[StudyAreaColumn.STUDY_AREA_ID]) - set(
            level_df[StudyAreaColumn.STUDY_AREA_ID]
        )
        if missing_metros:
            raise ValueError(
                f"Top-ten metros lack complete {level} entropy: {sorted(missing_metros)}"
            )

    data_directory.mkdir(parents=True, exist_ok=True)
    histories_df.to_parquet(data_directory / "entropy_histories.parquet", index=False)
    top_10_metros_df.to_parquet(data_directory / "top_10_metros.parquet", index=False)
