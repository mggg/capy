"""Prepare population-share cohorts and fitted score relationships."""

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
    PopulationComparison,
)
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import PipelineConfig

from national_figures.prepare_national_results import (
    IDENTITY_COLUMNS,
    PRIMARY_METRICS,
    read_national_figure_inputs,
    select_complete_histories,
)


def select_composition_histories(
    scores_df: pd.DataFrame, graph_summary_df: pd.DataFrame, years: list[int]
) -> pd.DataFrame:
    """Keep tract histories with retained population above 100,000 in every year.

    Args:
        scores_df (pd.DataFrame): One metric's White–Black tract scores.
        graph_summary_df (pd.DataFrame): Graph accounting with retained population by year and level.
        years (list[int]): Required Census years.

    Returns:
        pd.DataFrame: Complete histories with retained counts and Black/(White+Black) share rho.

    Raises:
        ValueError: Score or graph identities repeat.
    """
    complete_df = select_complete_histories(scores_df, years)
    complete_df = complete_df.merge(
        graph_summary_df[
            [*IDENTITY_COLUMNS, "retained_TOTPOP", "retained_WHITE", "retained_BLACK"]
        ],
        on=IDENTITY_COLUMNS,
        how="left",
        validate="one_to_one",
    )

    if complete_df[["retained_TOTPOP", "retained_WHITE", "retained_BLACK"]].isna().to_numpy().any():
        raise ValueError("Composition histories lack retained population accounting")

    minimum_population = pd.Series(
        complete_df.groupby(StudyAreaColumn.STUDY_AREA_ID)["retained_TOTPOP"].min()
    )
    eligible_ids = minimum_population.loc[minimum_population.gt(100000)].index.to_list()
    selected_df = complete_df.loc[
        complete_df[StudyAreaColumn.STUDY_AREA_ID].isin(eligible_ids)
    ].copy()
    selected_df["rho"] = selected_df["retained_BLACK"] / (
        selected_df["retained_WHITE"] + selected_df["retained_BLACK"]
    )

    return selected_df


def prepare_population_composition_data(
    config: PipelineConfig, repository_root: Path, data_directory: Path
) -> None:
    """Save complete White–Black tract cohorts and fitted line endpoints for configured years.

    Population must exceed 100,000 in every year. Fits use Black/(White+Black) shares and
    finite scores for a fixed cohort per metric.

    Args:
        config (PipelineConfig): Years, primary scores, and pipeline input directories.
        repository_root (Path): Base for configured relative input paths.
        data_directory (Path): Destination for composition_rows and composition_fits Parquets.

    Raises:
        OSError: Reading inputs or writing prepared tables fails.
        ValueError: Tracts or White–Black are unselected, or a fit lacks distinct shares.
    """
    if (
        GeographyLevel.TRACT not in config.census_geography_levels
        or PopulationComparison.WHITE_BLACK not in config.population_comparisons
    ):
        raise ValueError("Population composition requires configured White–Black tracts")

    years: list[int] = sorted(set(config.census_geography_years))
    history_years_by_selection = {(PopulationComparison.WHITE_BLACK, GeographyLevel.TRACT): years}
    metrics_df, definitions_df, graph_summary_df = read_national_figure_inputs(
        config, repository_root, history_years_by_selection
    )
    eligible_ids = definitions_df.loc[
        definitions_df[StudyAreaColumn.DEFINITION_POPULATION].gt(100000),
        StudyAreaColumn.STUDY_AREA_ID,
    ]
    selected_df = metrics_df.loc[
        metrics_df[MetricColumn.COMPARISON].eq(PopulationComparison.WHITE_BLACK)
        & metrics_df[StudyAreaColumn.STUDY_AREA_ID].isin(eligible_ids)
    ]
    metric_names = [metric for metric in PRIMARY_METRICS if metric in config.metric_names]

    if not metric_names:
        raise ValueError("Population composition requires at least one primary metric")

    composition_tables = []
    fitted_line_tables = []

    for metric in metric_names:
        histories_df = select_composition_histories(
            selected_df.loc[selected_df[MetricColumn.METRIC].eq(metric)], graph_summary_df, years
        )
        composition_tables.append(histories_df)
        fitted_line_tables.append(fit_composition_lines(histories_df, metric, years))

    composition_df = pd.concat(composition_tables, ignore_index=True)
    fits_df = pd.concat(fitted_line_tables, ignore_index=True)

    data_directory.mkdir(parents=True, exist_ok=True)
    composition_df.to_parquet(data_directory / "composition_rows.parquet", index=False)
    fits_df.to_parquet(data_directory / "composition_fits.parquet", index=False)


def fit_composition_lines(
    histories_df: pd.DataFrame, metric: MetricName, years: list[int]
) -> pd.DataFrame:
    """Fit one metric against Black population share in each year and return line endpoints.

    Args:
        histories_df (pd.DataFrame): One metric's complete cohort, with rho and finite scores.
        metric (MetricName): Score represented by the supplied cohort.
        years (list[int]): Census years to fit, in output order.

    Returns:
        pd.DataFrame: Fitted values at each year's minimum and maximum observed share.

    Raises:
        ValueError: A requested year has fewer than two distinct population shares.
    """
    fitted_line_tables = []

    for year in years:
        yearly_df = histories_df.loc[histories_df[MembershipColumn.CENSUS_YEAR].eq(year)]

        if yearly_df["rho"].nunique() < 2:
            raise ValueError(f"Composition fit needs distinct population shares in {year}")

        slope, intercept = np.polyfit(yearly_df["rho"], yearly_df[MetricColumn.VALUE], 1)
        endpoint_shares = np.array([yearly_df["rho"].min(), yearly_df["rho"].max()])
        yearly_fits_df = pd.DataFrame(
            {
                MetricColumn.METRIC: metric,
                MembershipColumn.CENSUS_YEAR: year,
                "rho": endpoint_shares,
                MetricColumn.VALUE: intercept + slope * endpoint_shares,
            }
        )
        fitted_line_tables.append(yearly_fits_df)

    return pd.concat(fitted_line_tables, ignore_index=True)
