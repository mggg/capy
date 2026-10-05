"""Prepare population tables ranked independently by each selection's Capy scores."""

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
from national_pipeline.pipeline_config import PipelineConfig

from national_figures.prepare_national_results import (
    PRIMARY_METRICS,
    check_figure_score_selection,
    read_national_figure_inputs,
    select_figure_years_by_selection,
)


def build_ranked_population_table(
    scores_df: pd.DataFrame,
    definitions_df: pd.DataFrame,
    graph_summary_df: pd.DataFrame,
    comparison: PopulationComparison = PopulationComparison.WHITE_BLACK,
) -> pd.DataFrame:
    """Build the 100 highest finite Capy scores and population counts for one selection.

    Ties are broken by area ID. Population is the retained graph total in millions; the second
    group's share uses total retained population, including groups outside the comparison.
    Undefined supplementary scores remain null and do not exclude an area.

    Args:
        scores_df (pd.DataFrame): Selected primary scores for one year, level, and comparison.
        definitions_df (pd.DataFrame): Study-area IDs and names.
        graph_summary_df (pd.DataFrame): Matching year/level retained population accounting.
        comparison (PopulationComparison): Determines the second-group population column; defaults
            to White–Black.

    Returns:
        pd.DataFrame: Rank, area identity, selected scores, population, and second-group share.

    Raises:
        ValueError: Identities repeat or ranked areas lack definitions or population accounting.
        KeyError: Capy or a required population column is absent.
    """
    values_df = scores_df.pivot(
        index=StudyAreaColumn.STUDY_AREA_ID,
        columns=MetricColumn.METRIC,
        values=MetricColumn.VALUE,
    ).replace([np.inf, -np.inf], np.nan)
    table_df = (
        values_df.reset_index()
        .dropna(subset=[MetricName.CAPY])
        .sort_values([MetricName.CAPY, StudyAreaColumn.STUDY_AREA_ID], ascending=[False, True])
        .head(100)
    )
    table_df = table_df.merge(
        definitions_df[[StudyAreaColumn.STUDY_AREA_ID, StudyAreaColumn.NAME]],
        on=StudyAreaColumn.STUDY_AREA_ID,
        how="left",
        validate="one_to_one",
    )
    if bool(table_df[StudyAreaColumn.NAME].isna().any()):
        raise ValueError("Ranked areas lack a study-area name")

    second_group_column = f"retained_{comparison.second_population_column}"
    population_columns = ["retained_TOTPOP", second_group_column]
    table_df = table_df.merge(
        graph_summary_df[[StudyAreaColumn.STUDY_AREA_ID, *population_columns]],
        on=StudyAreaColumn.STUDY_AREA_ID,
        how="left",
        validate="one_to_one",
    )
    if table_df[population_columns].isna().to_numpy().any():
        raise ValueError("Ranked areas lack retained population accounting")

    table_df["population_millions"] = table_df["retained_TOTPOP"] / 1_000_000
    table_df["second_group_share_total_population"] = (
        table_df[second_group_column] / table_df["retained_TOTPOP"]
    )
    table_df.insert(0, "rank", np.arange(1, len(table_df) + 1))
    return table_df.drop(columns=population_columns)


def prepare_ranked_population_table(
    config: PipelineConfig, repository_root: Path, table_directory: Path
) -> None:
    """Save up to 100 Capy-ranked areas per configured year, level, and comparison.

    Definition population must exceed 100,000. Capy is required; other configured primary metrics
    appear as supplementary columns.

    Args:
        config (PipelineConfig): Selected study areas, years, levels, comparisons, and metrics.
        repository_root (Path): Base for configured relative input directories.
        table_directory (Path): Destination for top_100_capy.csv and top_100_capy.parquet.

    Raises:
        OSError: Reading inputs or saving the completed table fails.
        ValueError: Capy is unselected, selected records are missing, or a selection has no finite
            Capy scores among population-eligible areas.
    """
    if MetricName.CAPY not in config.metric_names:
        raise ValueError("The ranked population table requires selected Capy scores")

    selected_metrics = tuple(metric for metric in PRIMARY_METRICS if metric in config.metric_names)
    years_by_selection = select_figure_years_by_selection(config)
    metrics_df, definitions_df, graph_summary_df = read_national_figure_inputs(
        config, repository_root, years_by_selection
    )
    eligible_ids = definitions_df.loc[
        definitions_df[StudyAreaColumn.DEFINITION_POPULATION].gt(100000),
        StudyAreaColumn.STUDY_AREA_ID,
    ]
    selections = [
        (year, level, comparison)
        for (comparison, level), years in years_by_selection.items()
        for year in years
    ]
    table_parts = []

    for year, level, comparison in selections:
        selected_graphs_df = graph_summary_df.loc[
            graph_summary_df[MembershipColumn.CENSUS_YEAR].eq(year)
            & graph_summary_df[MembershipColumn.GEOGRAPHY_LEVEL].eq(level)
        ]
        if selected_graphs_df.empty:
            raise ValueError(f"No graph summary for {year} {level}")

        scores_df = metrics_df.loc[
            metrics_df[MembershipColumn.CENSUS_YEAR].eq(year)
            & metrics_df[MembershipColumn.GEOGRAPHY_LEVEL].eq(level)
            & metrics_df[MetricColumn.COMPARISON].eq(comparison)
            & metrics_df[MetricColumn.METRIC].isin(selected_metrics)
        ]
        score_selections_df = pd.DataFrame(
            {MetricColumn.COMPARISON: [comparison], MembershipColumn.GEOGRAPHY_LEVEL: [level]}
        )

        check_figure_score_selection(
            scores_df, selected_graphs_df, score_selections_df, selected_metrics
        )

        scores_df = scores_df.loc[scores_df[StudyAreaColumn.STUDY_AREA_ID].isin(eligible_ids)]
        if scores_df.empty:
            raise ValueError(f"No population-eligible scores for {year} {level} {comparison}")

        table_df = build_ranked_population_table(
            scores_df, definitions_df, selected_graphs_df, comparison
        )
        if table_df.empty:
            raise ValueError(f"No finite Capy scores for {year} {level} {comparison} ranking")

        table_df[MembershipColumn.CENSUS_YEAR] = year
        table_df[MembershipColumn.GEOGRAPHY_LEVEL] = level
        table_df[MetricColumn.COMPARISON] = comparison
        table_parts.append(table_df)

    combined_df = pd.concat(table_parts, ignore_index=True)
    table_directory.mkdir(parents=True, exist_ok=True)
    combined_df.to_parquet(table_directory / "top_100_capy.parquet", index=False)
    combined_df.to_csv(table_directory / "top_100_capy.csv", index=False)
