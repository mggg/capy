"""Load the shared input selections, output folders, and execution settings from YAML."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from capy_core.geography_types import GeographyLevel, StudyAreaType

from .retrieve_data.raw_file_requests import (
    CensusYear,
    validate_relative_file_path,
)


class RawDataSubdirectories(BaseModel):
    """Names of folders inside the main raw-data directory.

    Attributes:
        census_population_tables (str): Census population tables for 2000 onward. Defaults to
            census.
        nhgis_population_and_boundaries (str): Historical population and boundary ZIP files.
            Defaults to nhgis.
        census_boundary_files (str): Census TIGER/Line boundary ZIP files. Defaults to tiger.
        original_1980_boundary_files (str): Original TIGER 1992 county archives used to restore
            twelve omitted 1980 BNA outlines. Defaults to tiger_1992.
        original_1990_block_references (str): Original STF1B and PL files that establish empty
            1990 land blocks omitted from NHGIS population tables. Defaults to census_1990_blocks.
        population_reference_tables (str): Published totals used to check population counts.
            Defaults to population_reference_tables.
        metro_membership_tables (str): Workbook listing the counties in each metro area. Defaults
            to metro_membership_tables.
        saved_nhgis_requests (str): Saved NHGIS request details and extract numbers, so unfinished
            downloads can be continued later. Defaults to saved_nhgis_requests.

    A name can include subfolders, such as tables/census. It cannot be an absolute path or
    use '..' to leave the raw-data directory. The filenames and folders for years, geography
    levels, and states are chosen by the request builders.
    """

    # Reject misspelled settings and prevent reassignment after loading the YAML.
    model_config = ConfigDict(extra="forbid", frozen=True)
    census_population_tables: str = "census"
    nhgis_population_and_boundaries: str = "nhgis"
    census_boundary_files: str = "tiger"
    original_1980_boundary_files: str = "tiger_1992"
    original_1990_block_references: str = "census_1990_blocks"
    population_reference_tables: str = "population_reference_tables"
    metro_membership_tables: str = "metro_membership_tables"
    saved_nhgis_requests: str = "saved_nhgis_requests"

    @field_validator("*")
    @classmethod
    def validate_relative_directory(cls, value: str) -> str:
        """Apply the same relative-directory check to every folder setting."""
        return validate_relative_file_path(value)


class PipelineConfig(BaseModel):
    """Choose pipeline inputs, file locations, and retrieval settings for a complete run.

    The geography levels and years describe the units to analyze. Study-area settings describe the
    enclosing areas, which may need additional county or city data. Request preparation combines
    both selections and checks that they are supported before any retrieval starts.

    Attributes:
        census_geography_levels (tuple[GeographyLevel, ...]): Units that will become graph nodes:
            counties, tracts, block_groups, or blocks. Defaults to all four; cannot be empty.
        census_geography_years (tuple[CensusYear, ...]): Census years for those units. Defaults to
            all five decades from 1980 through 2020; cannot be empty. No 1980 blocks or block
            groups are requested because their boundaries are unsupported.
        study_area_type (StudyAreaType): county, cbsa, max_county, or max_city. Defaults to
            max_city. All modes need county data to define the enclosing areas; max_city also
            needs city and 2020 block data for population-based selection.
        study_area_vintage (CensusYear): Year of the boundaries and populations defining those
            areas. Defaults to 2020. max_city supports only 2020. Metro membership uses the
            separately defined March 2020 workbook regardless of this boundary vintage.
        raw_data_directory (Path): Directory for raw files and NHGIS submission records. Defaults
            to data/raw. Relative paths start at the repository root.
        raw_data_subdirectories (RawDataSubdirectories): Folders beneath raw_data_directory.
            Omitted folder settings use the defaults documented on RawDataSubdirectories.
        processed_population_directory (Path): Folder for derived population Parquet files.
            Defaults to data/processed/population. Relative paths start at the repository root.
        joined_geography_directory (Path): Folder for population-attributed boundaries and join
            accounting. Defaults to data/processed/geography. Relative paths start at the
            repository root; this folder must be separate from raw and population folders.
        study_area_directory (Path): Definitions, candidate scores, and Census-unit memberships.
            Defaults to data/processed/study_areas. Relative paths start at the repository root;
            this folder must be separate from raw, population, and joined-geography folders.
        env_file (Path | None): Optional file of environment variables, such as API keys. Defaults
            to None. Relative paths start at the repository root. Online retrieval reads it
            without replacing existing environment variables; offline runs do not read it.
        offline (bool): Reuse files in the configured folders without downloading. Defaults to
            False.
        raw_checksums_file (Path): Where to write the checksum list, relative to the repository
            root. Defaults to data/raw_checksums.sha256. Written only by the checksum command.
        file_path_patterns (tuple[str, ...]): Exact or wildcard destination paths to select, such
            as census/2020/*. Defaults to ("*",), selecting all files needed by the run. Each
            pattern must match a configured file. Narrower patterns make a partial download and
            can leave out data needed for later stages.
        max_parallel_downloads (int): Maximum simultaneous file retrievals, including local reuse.
            Defaults to 4; must be at least 1. Use 1 for sequential retrieval.
        nhgis_retry_interval_seconds (int): Wait between rounds of pending-extract checks.
            Defaults to 60; must be at least 1.
        nhgis_max_wait_minutes (int): Time allowed for pending-extract retries after the initial
            retrieval batches finish. Defaults to 60; zero disables retries. Each wait is capped
            by the time remaining, but the following round, including queued files, may finish
            after the limit.
    """

    model_config = ConfigDict(
        extra="forbid",  # Reject unrecognized settings, including spelling mistakes.
        validate_assignment=True,  # Check overrides using the same rules as loaded settings.
    )
    census_geography_levels: tuple[GeographyLevel, ...] = Field(
        default=(
            GeographyLevel.COUNTY,
            GeographyLevel.TRACT,
            GeographyLevel.BLOCK_GROUP,
            GeographyLevel.BLOCK,
        ),
        min_length=1,
    )
    census_geography_years: tuple[CensusYear, ...] = Field(
        default=(1980, 1990, 2000, 2010, 2020), min_length=1
    )
    study_area_type: StudyAreaType = StudyAreaType.MAX_CITY
    study_area_vintage: CensusYear = 2020
    raw_data_directory: Path = Path("data/raw")
    raw_data_subdirectories: RawDataSubdirectories = Field(default_factory=RawDataSubdirectories)
    processed_population_directory: Path = Path("data/processed/population")
    joined_geography_directory: Path = Path("data/processed/geography")
    study_area_directory: Path = Path("data/processed/study_areas")
    env_file: Path | None = None
    offline: bool = False
    raw_checksums_file: Path = Path("data/raw_checksums.sha256")
    file_path_patterns: tuple[str, ...] = ("*",)
    # Field supplies the default and inclusive lower limit (ge).
    max_parallel_downloads: int = Field(default=4, ge=1)
    nhgis_retry_interval_seconds: int = Field(default=60, ge=1)
    nhgis_max_wait_minutes: int = Field(default=60, ge=0)

    @field_validator("census_geography_levels")
    @classmethod
    def validate_graph_node_levels(
        cls, levels: tuple[GeographyLevel, ...]
    ) -> tuple[GeographyLevel, ...]:
        """Reject state or place selections with ValueError; neither is a graph-node resolution."""
        if GeographyLevel.STATE in levels or GeographyLevel.PLACE in levels:
            raise ValueError("Graph nodes must be counties, tracts, block_groups, or blocks")

        return levels


def load_configuration(path: Path) -> PipelineConfig:
    """Read a YAML configuration, check individual settings, and fill in omitted defaults.

    This opens only the YAML file, not any of the requested data files. Paths in the settings are
    left as written: most start at the repository root, while raw-data subfolders start inside
    raw_data_directory. Combinations of years, levels, and study areas are checked when building
    requests. A relative path supplied on the command line starts at the shell's current
    directory.

    Args:
        path (Path): YAML filename. Relative filenames start at the shell's current directory.

    Returns:
        PipelineConfig: Settings with defaults for omitted optional fields.

    Raises:
        OSError: The configuration cannot be read.
        ValueError: YAML syntax or configuration fields are invalid. The message identifies the
            file and the affected setting or YAML line.
    """
    content = path.read_text()
    try:
        settings = yaml.safe_load(content)
    except yaml.MarkedYAMLError as error:
        line = error.problem_mark.line + 1 if error.problem_mark is not None else "unknown"
        raise ValueError(f"Invalid YAML in {path}, line {line}: {error.problem}") from None
    except yaml.YAMLError:
        raise ValueError(f"Invalid YAML in {path}") from None

    try:
        return PipelineConfig.model_validate(settings)
    except ValidationError as error:
        problems = []
        for issue in error.errors(include_input=False, include_url=False):
            setting = ".".join(str(part) for part in issue["loc"]) or "document"
            problems.append(f"{setting}: {issue['msg']}")

        raise ValueError(f"Invalid configuration {path}: {'; '.join(problems)}") from None
