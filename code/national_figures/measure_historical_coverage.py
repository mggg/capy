"""Measure mapped 1980 tract population against the fixed metro's county population."""

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
from national_pipeline.derived_file_paths import build_population_output_path
from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import PipelineConfig

MINIMUM_1980_POPULATION_COVERAGE = 0.9
# Dade was renamed Miami-Dade in 1997; this is a code change, not a population allocation.
# https://www.census.gov/programs-surveys/geography/technical-documentation/county-changes.1990.html
COUNTY_CODES_IN_1980 = {"12086": "12025"}


@dataclass(frozen=True)
class HistoricalCoverage:
    """A fixed metro's 1980 population accounting and eligibility for tract histories.

    Missing counts remain None. The numerator precedes the graph population filter; the
    denominator sums original 1980 populations for the definition's member county codes.
    The Dade/Miami-Dade code change is resolved explicitly. Other missing historical county
    codes are reported without a geographic crosswalk or imputation.
    """

    study_area_id: str
    assigned_tract_population: int | None
    member_county_population: int | None
    population_county_codes: str
    missing_county_codes: str
    coverage_fraction: float | None
    minimum_coverage: float
    eligible: bool
    status: str


def read_1980_cbsa_coverage(
    config: PipelineConfig, repository_root: Path, definitions_df: pd.DataFrame
) -> pd.DataFrame:
    """Read 1980 county totals and assigned tract counts for the configured fixed metros.

    Args:
        config (PipelineConfig): Population and study-area directories and definition vintage.
        repository_root (Path): Base for configured relative directories.
        definitions_df (pd.DataFrame): Metro IDs and their county_codes collections.

    Returns:
        pd.DataFrame: One coverage and eligibility record per supplied metro.

    Raises:
        OSError: A population table or assignment summary cannot be read.
        ValueError: County or tract identities repeat or counts are invalid.
    """
    state_codes = sorted(
        {
            county_code[:2]
            for county_codes in definitions_df.county_codes
            for county_code in county_codes
        }
    )
    county_tables = []

    for state_code in state_codes:
        # Puerto Rico has no supported 1980 source; its missing counties remain explicit.
        if state_code == "72":
            continue

        path = (
            repository_root
            / config.processed_population_directory
            / build_population_output_path(1980, GeographyLevel.COUNTY, state_code)
        )
        counties_df = pd.read_parquet(path, columns=["STATEA", "COUNTYA", "TOTPOP"])
        counties_df["county_code"] = counties_df.STATEA + counties_df.COUNTYA
        county_tables.append(counties_df[["county_code", "TOTPOP"]])

    county_population_df = (
        pd.concat(county_tables, ignore_index=True)
        if county_tables
        else pd.DataFrame(columns=pd.Index(["county_code", "TOTPOP"]))
    )
    assignment_path = (
        repository_root
        / config.study_area_directory
        / config.study_area_type
        / str(config.study_area_vintage)
        / "summary.parquet"
    )
    assignments_df = pd.read_parquet(assignment_path)
    tract_population_df = assignments_df.loc[
        assignments_df.census_year.eq(1980) & assignments_df.geography_level.eq("tracts"),
        ["study_area_id", "TOTPOP"],
    ]

    return measure_1980_cbsa_coverage(definitions_df, tract_population_df, county_population_df)


def measure_1980_cbsa_coverage(
    definitions_df: pd.DataFrame,
    tract_population_df: pd.DataFrame,
    county_population_df: pd.DataFrame,
) -> pd.DataFrame:
    """Determine a fixed 90% population-coverage cohort before graph population filtering.

    The same eligibility applies to every year, metric, and population comparison in a tract
    history containing 1980. Ratios above one are retained for inspection, not clipped: county
    code matching and representative-point tract assignment are not a historical crosswalk.

    Args:
        definitions_df (pd.DataFrame): Unique study_area_id and nonempty county_codes collections.
        tract_population_df (pd.DataFrame): Unique study_area_id and assigned 1980 TOTPOP, before
            removal of units with no White or Black population. Null means unavailable.
        county_population_df (pd.DataFrame): Unique five-digit county_code and 1980 TOTPOP.

    Returns:
        pd.DataFrame: Counts, missing county codes, ratio, threshold, eligibility, and status.
            Missing inputs and nonpositive denominators are ineligible, not treated as zero.

    Raises:
        ValueError: IDs repeat, county rosters are empty/repeated, or counts are not finite,
            nonnegative whole-person counts.
    """
    for population_df, identity in (
        (definitions_df, "study_area_id"),
        (tract_population_df, "study_area_id"),
        (county_population_df, "county_code"),
    ):
        if bool(population_df[identity].isna().any()) or bool(
            population_df[identity].duplicated().any()
        ):
            raise ValueError(f"Coverage requires unique, nonmissing {identity} values")

    for population_df in (tract_population_df, county_population_df):
        counts = population_df.TOTPOP.dropna()
        if not counts.between(0, float("inf"), inclusive="left").all() or counts.mod(1).ne(0).any():
            raise ValueError("Coverage populations must be finite, nonnegative whole-person counts")

    county_populations = county_population_df.set_index("county_code").TOTPOP
    tract_populations = tract_population_df.set_index("study_area_id").TOTPOP
    records = []

    for study_area_id, member_county_codes in zip(
        definitions_df["study_area_id"], definitions_df["county_codes"]
    ):
        county_codes: list[str] = list(member_county_codes)
        if not county_codes or len(county_codes) != len(set(county_codes)):
            raise ValueError("Coverage requires a nonempty, unique member-county roster")

        population_county_codes = [COUNTY_CODES_IN_1980.get(code, code) for code in county_codes]
        if len(population_county_codes) != len(set(population_county_codes)):
            raise ValueError("County code changes must not count the same 1980 county twice")

        county_counts = county_populations.reindex(population_county_codes)
        missing_codes = county_counts.index[county_counts.isna()].tolist()
        denominator = None if missing_codes else int(county_counts.sum())
        assigned_population = tract_populations.get(study_area_id)
        numerator = None if pd.isna(assigned_population) else int(assigned_population)
        fraction = None

        if denominator is None:
            status = "missing_county_population"
        elif denominator == 0:
            status = "zero_county_population"
        elif numerator is None:
            status = "missing_tract_population"
        else:
            fraction = numerator / denominator
            status = (
                "eligible" if fraction >= MINIMUM_1980_POPULATION_COVERAGE else "below_threshold"
            )

        records.append(
            HistoricalCoverage(
                study_area_id=study_area_id,
                assigned_tract_population=numerator,
                member_county_population=denominator,
                population_county_codes=",".join(population_county_codes),
                missing_county_codes=",".join(missing_codes),
                coverage_fraction=fraction,
                minimum_coverage=MINIMUM_1980_POPULATION_COVERAGE,
                eligible=status == "eligible",
                status=status,
            )
        )

    return pd.DataFrame([asdict(record) for record in records])


def compare_coverage_cohort_means(
    unrestricted_df: pd.DataFrame, restricted_df: pd.DataFrame
) -> pd.DataFrame:
    """Compare equal-area mean scores and cohort sizes with and without the coverage cutoff.

    Inputs are complete trajectory rows with all other selection rules already applied.
    Each output row identifies a comparison, resolution, metric, and Census year.
    """
    selection_columns = ["population_comparison", "geography_level", "metric", "census_year"]
    summaries = []

    for trajectories_df in (unrestricted_df, restricted_df):
        summaries.append(
            trajectories_df.groupby(selection_columns).agg(
                area_count=("study_area_id", "nunique"), mean_score=("value", "mean")
            )
        )

    comparison_df = summaries[0].join(summaries[1], lsuffix="_unrestricted", rsuffix="_restricted")
    comparison_df["mean_score_change"] = (
        comparison_df.mean_score_restricted - comparison_df.mean_score_unrestricted
    )
    return comparison_df.reset_index()
