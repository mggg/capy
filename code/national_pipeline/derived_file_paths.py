"""Shared output paths and study-area labels for pipeline results."""

from pathlib import Path

import us

from national_pipeline.geography_types import GeographyLevel
from national_pipeline.pipeline_config import PipelineConfig


def build_study_area_label(config: PipelineConfig) -> str:
    """Return the uppercase study-area type and two-digit vintage, such as CBSA20."""
    return f"{config.study_area_type.upper()}{config.study_area_vintage % 100:02d}"


def build_population_output_path(
    census_year: int, geography_level: GeographyLevel, state_code: str | None = None
) -> Path:
    """Build a relative Parquet path using the Census year, geography level, and state.

    For example, 1990 tracts with state code "10" produce
    ``1990/tracts/DE_1990_populations.parquet``.

    Args:
        census_year (int): Census year used in the folder and filename.
        geography_level (GeographyLevel): Geographic units represented by the table.
        state_code (str | None): Two-digit state FIPS code, including its leading zero. Defaults
            to None for a national table, whose filename starts with "national".

    Returns:
        Path: Table path relative to the configured processed-population directory.

    Raises:
        ValueError: The supplied state code has no known postal abbreviation.
    """
    area_name = "national"

    if state_code is not None:
        state_abbreviations_by_fips = us.states.mapping("fips", "abbr")

        if state_code not in state_abbreviations_by_fips:
            raise ValueError(f"Unknown state FIPS code: {state_code}")

        area_name = state_abbreviations_by_fips[state_code]

    filename = f"{area_name}_{census_year}_populations.parquet"

    return Path(str(census_year)) / geography_level.value / filename


def build_join_output_paths(population_relative_path: Path) -> tuple[Path, Path, Path]:
    """Build the three output names from a processed population table's relative path.

    Args:
        population_relative_path (Path): Path beneath the population folder, such as
            2020/tracts/DE_2020_populations.parquet.

    Returns:
        tuple[Path, Path, Path]: Matched geography, unmatched population, and unmatched boundary
            paths, in that order, beneath the joined-geography folder. The year/level folders
            and state/year filename prefix are preserved.
    """
    state_year = population_relative_path.stem.removesuffix("_populations")

    return (
        population_relative_path.with_name(f"{state_year}_geography.parquet"),
        population_relative_path.with_name(f"{state_year}_unmatched_population.parquet"),
        population_relative_path.with_name(f"{state_year}_unmatched_boundaries.parquet"),
    )


def build_membership_output_path(population_relative_path: Path) -> Path:
    """Build the membership filename corresponding to a processed population table.

    Args:
        population_relative_path (Path): Path beneath the population folder, such as
            2020/tracts/DE_2020_populations.parquet.

    Returns:
        Path: Relative path beneath a study-area type/vintage's memberships folder. The year,
            level, and state prefix are preserved.
    """
    state_year = population_relative_path.stem.removesuffix("_populations")

    return population_relative_path.with_name(f"{state_year}_memberships.parquet")
