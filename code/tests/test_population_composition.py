"""Population shares and complete-year composition cohorts."""

import numpy as np
import pandas as pd
import pytest
from national_figures.prepare_population_composition import (
    fit_composition_lines,
    select_composition_histories,
)
from national_pipeline.compute_metrics.metric_types import MetricName

HISTORY_YEARS = [1980, 1990, 2000, 2010, 2020]


def test_composition_requires_population_threshold_in_every_decade():
    rows = []
    outcomes = []

    for area_id in ("always_large", "grew_large", "missing_decade"):
        for year in HISTORY_YEARS:
            if area_id == "missing_decade" and year == 1990:
                continue

            identity = {"study_area_id": area_id, "census_year": year, "geography_level": "tracts"}
            rows.append({**identity, "value": 0.6})
            outcomes.append(
                {
                    **identity,
                    "retained_TOTPOP": 100000
                    if area_id == "grew_large" and year == 1980
                    else 200000,
                    "retained_WHITE": 120000,
                    "retained_BLACK": 30000,
                }
            )

    composition_df = select_composition_histories(
        pd.DataFrame(rows), pd.DataFrame(outcomes), HISTORY_YEARS
    )
    assert composition_df.study_area_id.unique().tolist() == ["always_large"]
    assert composition_df.census_year.tolist() == HISTORY_YEARS
    np.testing.assert_allclose(composition_df.rho, 0.2)


def test_composition_fits_preserve_year_order_and_observed_share_extents():
    histories_df = pd.DataFrame(
        {
            "census_year": [1980, 1980, 1980, 2020, 2020, 2020],
            "rho": [0.1, 0.3, 0.5, 0.2, 0.4, 0.6],
            "value": [0.3, 0.5, 0.7, 0.8, 0.7, 0.6],
        }
    )
    original_df = histories_df.copy(deep=True)

    fits_df = fit_composition_lines(histories_df, MetricName.CAPY, [2020, 1980])

    assert fits_df.metric.tolist() == [MetricName.CAPY] * 4
    assert fits_df.census_year.tolist() == [2020, 2020, 1980, 1980]
    np.testing.assert_allclose(fits_df.rho, [0.2, 0.6, 0.1, 0.5])
    np.testing.assert_allclose(fits_df.value, [0.8, 0.6, 0.3, 0.7])
    pd.testing.assert_frame_equal(histories_df, original_df)


@pytest.mark.parametrize("year", [1980, 2020])
def test_composition_fit_rejects_constant_shares_or_missing_year(year):
    histories_df = pd.DataFrame(
        {"census_year": [1980, 1980], "rho": [0.2, 0.2], "value": [0.3, 0.5]}
    )

    with pytest.raises(ValueError, match=f"distinct population shares in {year}"):
        fit_composition_lines(histories_df, MetricName.CAPY, [year])
