"""Average each metric over a fixed set of areas with a defined value in every expected year."""

from typing import cast

import numpy as np
import pandas as pd

from capy_core.assign_study_areas.study_area_columns import MembershipColumn, StudyAreaColumn
from capy_core.geography_types import GeographyLevel

from .metric_types import MetricColumn


def average_when_all_years_present(
    metric_values_df: pd.DataFrame, expected_years_by_level: dict[GeographyLevel, tuple[int, ...]]
) -> pd.DataFrame:
    """Build yearly unweighted area means using a separate complete-history cohort per metric.

    Args:
        metric_values_df (pd.DataFrame): One row per area/year/level/comparison/metric, with
            undefined values left null. Inputs are not changed.
        expected_years_by_level (dict[GeographyLevel, tuple[int, ...]]): Explicit selected years
            for each resolution, excluding unsupported 1980 blocks and block groups.

    Returns:
        pd.DataFrame: One mean per year/level/comparison/metric, with the contributing IDs, count,
            and expected years. Areas must have finite values in every expected year for that
            metric. Empty cohorts yield null means, and no population weighting is applied.

    Raises:
        ValueError: Rows repeat an area/year within a metric group, or contain unexpected years.
            A defined value is nonfinite.
    """
    group_columns = [MembershipColumn.GEOGRAPHY_LEVEL, MetricColumn.COMPARISON, MetricColumn.METRIC]
    mean_rows = []

    for group_labels, values_df in metric_values_df.groupby(group_columns, sort=True):
        level, comparison, metric = cast(tuple[str, str, str], group_labels)
        expected_years = expected_years_by_level[GeographyLevel(level)]
        identity_columns = [StudyAreaColumn.STUDY_AREA_ID, MembershipColumn.CENSUS_YEAR]

        if values_df.duplicated(identity_columns).any() or not bool(
            values_df[MembershipColumn.CENSUS_YEAR].isin(expected_years).all()
        ):
            raise ValueError(
                f"Metric rows repeat identities or contain unexpected years: {level} {comparison} {metric}"
            )

        if not np.isfinite(values_df[MetricColumn.VALUE].dropna().astype(float)).all():
            raise ValueError("Defined metric values must be finite before averaging")

        values_by_year_df = values_df.pivot(
            index=StudyAreaColumn.STUDY_AREA_ID,
            columns=MembershipColumn.CENSUS_YEAR,
            values=MetricColumn.VALUE,
        ).reindex(columns=expected_years)
        complete_values_df = values_by_year_df.dropna()
        contributing_area_ids = sorted(complete_values_df.index.tolist())

        for year in expected_years:
            mean_rows.append(
                {
                    MembershipColumn.CENSUS_YEAR: year,
                    MembershipColumn.GEOGRAPHY_LEVEL: level,
                    MetricColumn.COMPARISON: comparison,
                    MetricColumn.METRIC: metric,
                    MetricColumn.AVERAGE: None
                    if complete_values_df.empty
                    else float(complete_values_df[year].mean()),
                    MetricColumn.EXPECTED_YEARS: list(expected_years),
                    MetricColumn.CONTRIBUTING_AREA_IDS: contributing_area_ids,
                    MetricColumn.AREA_COUNT: len(contributing_area_ids),
                }
            )

    return pd.DataFrame(mean_rows)
