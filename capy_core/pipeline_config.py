"""
Load pipeline settings and resolve input and output paths from a YAML configuration.

Usage from Python:
    from pathlib import Path
    from capy_core.pipeline_config import load_config
    config = load_config(Path("capy_core/config.yaml"))
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import yaml

SUPPORTED_YEARS = {1980, 1990, 2000, 2010, 2020}
STUDY_AREA_TYPES = {"cbsa", "county", "max_city", "max_county"}
CENSUS_GEOGRAPHY_TYPES = {"tracts", "block_groups", "blocks", "counties"}

StudyAreaType = Literal["cbsa", "county", "max_city", "max_county"]
CensusGeographyType = Literal["tracts", "block_groups", "blocks", "counties"]
SourceGeographyType = Literal["tracts", "block_groups", "blocks", "counties", "places"]


@dataclass(frozen=True, slots=True)
class PipelineSettings:
    """Validated user settings, with paths still relative to their configured bases.

    Attributes:
        study_area_type (StudyAreaType): Type of study area to analyze.
        census_geography_type (CensusGeographyType): Type of census geography to use for
            dual-graph construction.
        census_geography_years (tuple[int, ...]): Census years for which boundaries are needed
            for the selected geography type.
        study_area_source_path (Path | None): Path to the CSV delineating study areas,
            or None for county mode.
        study_area_vintage (int): Census year for which the study-area definitions are selected.
        study_area_label (str): Label for the study-area definition, used in output paths.
        repo_root_path (Path | None): Base path for resolving relative paths in the settings,
            or None to use the parent of the directory containing the config file.
        data_root_path (Path): Base path for raw and processed pipeline data.
        output_root_path (Path): Base path beneath which run-specific results are stored.
        figure_root_path (Path): Base path beneath which run-specific figures are stored.
        env_file_path (Path): Path to the credentials file (does not need to exist yet).
        parallel_graph_workers (int): Number of processes to use for parallel graph construction.
    """

    study_area_type: StudyAreaType
    census_geography_type: CensusGeographyType
    census_geography_years: tuple[int, ...]
    study_area_source_path: Path | None
    study_area_vintage: int
    study_area_label: str
    repo_root_path: Path | None
    data_root_path: Path
    output_root_path: Path
    figure_root_path: Path
    env_file_path: Path
    parallel_graph_workers: int


@dataclass(frozen=True, slots=True)
class GeographyRequest:
    """One year and geography level required for source preparation.

    Attributes:
        year (int): Census year for which boundaries are needed.
        geography (SourceGeographyType): Type of geography to prepare for that year.
    """

    year: int
    geography: SourceGeographyType


@dataclass(frozen=True, slots=True)
class ResolvedConfig:
    """Configuration object that provides the pipeline with validated settings and resolved paths.

    Properties derive the effective census years, definition geography, and shared input and
    output paths so stages use the same conventions. Use load_config() to construct this object
    from YAML; the class itself does not load files or validate its constructor arguments.

    It is the responsibility of each pipeline stage to create its output directories and files.
    Resolving the configuration computes their paths without creating them.

    Attributes:
        settings (PipelineSettings): Validated user settings, retaining paths as configured.
        repo_root_path (Path): Absolute base for resolving relative paths in the settings.
        data_root_path (Path): Absolute base for raw and processed pipeline data.
        output_root_path (Path): Absolute base beneath which run-specific results are stored.
        figure_root_path (Path): Absolute base beneath which run-specific figures are stored.
        env_file_path (Path): Absolute path to the credentials file, which need not exist yet.
        study_area_source_path (Path | None): Absolute path to the selected delineation CSV,
            or None for county mode.

    Properties:
        effective_years (tuple[int, ...]): Requested census years in their original order,
            excluding 1980 for blocks and block groups, which lack boundaries for that year.
        definition_geography_type (SourceGeographyType): Places for max-city definitions,
            counties for all other study-area types.
        raw_population_path (Path): Directory for raw population data beneath data_root_path.
        raw_geographies_path (Path): Directory for raw boundary data beneath data_root_path.
        census_geographies_path (Path): Directory for processed census boundaries.
        study_area_definitions_path (Path): Directory for processed study-area definitions.
        selected_geographies_path (Path): Directory for census geographies clipped to study areas.
        graphs_path (Path): Directory for the resulting dual graphs.
        definition_geography_glob (str): Pattern matching processed definition boundaries
            for the configured study-area vintage and definition geography.
        definition_county_glob (str): Pattern matching processed county boundaries for the
            study-area vintage, including those needed alongside places in max-city mode.
        run_relative_path (Path): Run subdirectory combining geography and study-area type,
            study-area label, and sorted effective years.
        run_output_path (Path): Run-specific results directory beneath output_root_path.
        figure_output_path (Path): Run-specific figures directory beneath figure_root_path.
    """

    settings: PipelineSettings
    repo_root_path: Path
    data_root_path: Path
    output_root_path: Path
    figure_root_path: Path
    env_file_path: Path
    study_area_source_path: Path | None

    @property
    def effective_years(self) -> tuple[int, ...]:
        """Exclude years without boundaries while preserving the requested year order."""
        years = self.settings.census_geography_years

        if self.settings.census_geography_type in {"blocks", "block_groups"}:
            return tuple(year for year in years if year != 1980)

        return years

    @property
    def definition_geography_type(self) -> SourceGeographyType:
        return "places" if self.settings.study_area_type == "max_city" else "counties"

    @property
    def raw_population_path(self) -> Path:
        return self.data_root_path / "raw" / "population"

    @property
    def raw_geographies_path(self) -> Path:
        return self.data_root_path / "raw" / "geographies"

    @property
    def census_geographies_path(self) -> Path:
        return self.data_root_path / "processed" / "census_geographies"

    @property
    def study_area_definitions_path(self) -> Path:
        return self.data_root_path / "processed" / "study_area_definitions"

    @property
    def selected_geographies_path(self) -> Path:
        return self.data_root_path / "processed" / "clipped_geographies"

    @property
    def graphs_path(self) -> Path:
        return self.data_root_path / "processed" / "dual_graphs"

    @property
    def definition_geography_glob(self) -> str:
        geography = self.definition_geography_type
        year = self.settings.study_area_vintage

        return str(self.census_geographies_path / geography / f"{year}_{geography}_*.gpkg")

    @property
    def definition_county_glob(self) -> str:
        """County inputs also needed when selecting the largest city in each CBSA."""
        year = self.settings.study_area_vintage

        return str(self.census_geographies_path / "counties" / f"{year}_counties_*.gpkg")

    @property
    def run_relative_path(self) -> Path:
        geography = self.settings.census_geography_type
        study_area = self.settings.study_area_type
        year_label = "_".join(str(year) for year in sorted(self.effective_years))

        return Path(f"{geography}_in_{study_area}") / self.settings.study_area_label / year_label

    @property
    def run_output_path(self) -> Path:
        return self.output_root_path / self.run_relative_path

    @property
    def figure_output_path(self) -> Path:
        return self.figure_root_path / self.run_relative_path


def load_config(path: Path) -> ResolvedConfig:
    """Load and validate the pipeline configuration from a YAML file.

    Args:
        path (Path): Path to the YAML configuration file.

    Returns:
        ResolvedConfig: A dataclass containing the resolved configuration values.

    Raises:
        FileNotFoundError: If the configuration or required source CSV is missing.
        ValueError: If the YAML or a configuration setting is invalid.
    """
    resolved_path = path.resolve()

    try:
        with resolved_path.open(encoding="utf-8") as f:
            raw_yaml = yaml.safe_load(f)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Config file not found: {resolved_path}") from exc
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing YAML config file {resolved_path}: {e}") from e

    try:
        settings = parse_pipeline_settings(raw_yaml)
    except ValueError as exc:
        raise ValueError(f"Invalid configuration in {resolved_path}: {exc}") from exc

    return resolve_config(settings, resolved_path)


def parse_pipeline_settings(raw_yaml: object) -> PipelineSettings:
    """Parse raw YAML data into a PipelineSettings dataclass.

    Args:
        raw_yaml (object): The raw data loaded from the YAML file.

    Returns:
        PipelineSettings: A dataclass containing the parsed settings.

    Raises:
        ValueError: If the input is not a dictionary or if required fields are missing or invalid
    """
    if not isinstance(raw_yaml, dict):
        raise ValueError("Config YAML must be a mapping (dictionary)")  # noqa: TRY004

    validate_config_fields_exist(raw_yaml)
    study_area_type = raw_yaml["study_area_type"]
    census_geography_type = raw_yaml["census_geography_type"]

    if not isinstance(study_area_type, str) or study_area_type not in STUDY_AREA_TYPES:
        raise ValueError(f"Invalid study_area_type: {study_area_type!r}")

    if (
        not isinstance(census_geography_type, str)
        or census_geography_type not in CENSUS_GEOGRAPHY_TYPES
    ):
        raise ValueError(f"Invalid census_geography_type: {census_geography_type!r}")

    years = parse_census_years(raw_yaml["census_geography_years"])
    vintage = parse_study_area_vintage(raw_yaml.get("study_area_vintage", 2020))
    study_area_source_path = parse_study_area_source_path(
        raw_yaml["study_area_source"], study_area_type
    )
    repo_root = raw_yaml.get("repo_root")
    repo_root_path = None if repo_root is None else parse_path(repo_root, "repo_root")

    if census_geography_type in ("blocks", "block_groups") and years == (1980,):
        raise ValueError(f"No supported boundary years selected for {census_geography_type}")

    if study_area_type == "max_city" and vintage != 2020:
        raise ValueError("max_city currently requires study_area_vintage: 2020")

    return PipelineSettings(
        study_area_type=cast(StudyAreaType, study_area_type),
        census_geography_type=cast(CensusGeographyType, census_geography_type),
        census_geography_years=years,
        study_area_source_path=study_area_source_path,
        study_area_vintage=vintage,
        study_area_label=parse_study_area_label(raw_yaml["study_area_label"]),
        repo_root_path=repo_root_path,
        data_root_path=parse_path(raw_yaml.get("data_root", "data/shared"), "data_root"),
        output_root_path=parse_path(
            raw_yaml.get("output_root", "data/shared/outputs"), "output_root"
        ),
        figure_root_path=parse_path(raw_yaml.get("figure_root", "figures/baseline"), "figure_root"),
        env_file_path=parse_path(raw_yaml.get("env_file", ".env"), "env_file"),
        parallel_graph_workers=parse_parallel_graph_workers(
            raw_yaml.get("parallel_graph_workers", 6)
        ),
    )


def validate_config_fields_exist(raw_yaml: dict[object, object]) -> None:
    """Reject missing required settings and unrecognized configuration keys.

    Args:
        raw_yaml (dict[object, object]): The mapping loaded from YAML.

    Raises:
        ValueError: If required fields are missing or unknown fields are present.
    """
    required_fields = {
        "study_area_type",
        "census_geography_type",
        "census_geography_years",
        "study_area_source",
        "study_area_label",
    }
    allowed_fields = required_fields | {
        "study_area_vintage",
        "repo_root",
        "data_root",
        "output_root",
        "figure_root",
        "env_file",
        "parallel_graph_workers",
    }

    missing_fields = required_fields - raw_yaml.keys()
    unknown_fields = raw_yaml.keys() - allowed_fields

    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(sorted(missing_fields))}")

    if unknown_fields:
        field_names = ", ".join(sorted(str(field) for field in unknown_fields))
        raise ValueError(f"Unknown fields in config: {field_names}")


def parse_census_years(raw: object) -> tuple[int, ...]:
    """Parse and validate the census geography years from the raw YAML data.

    Args:
        raw (object): The raw data for census geography years.

    Returns:
        tuple[int,...]: A tuple of valid census geography years.

    Raises:
        ValueError: If the input is not a nonempty list of integers or contains unsupported years
        ValueError: If there are duplicate years in the input list
    """
    if not isinstance(raw, list) or not raw:
        raise ValueError("census_geography_years must be a nonempty list of integers")

    years: list[int] = []

    for year in raw:
        if type(year) is not int or year not in SUPPORTED_YEARS:
            raise ValueError(f"Unsupported census geography year: {year!r}")

        if year in years:
            raise ValueError(f"Duplicate census geography year: {year!r}")

        years.append(year)

    return tuple(years)


def parse_study_area_vintage(raw: object) -> int:
    """Parse and validate the study area vintage from the raw YAML data.

    Args:
        raw (object): The raw data for study area vintage.

    Returns:
        int: The validated study area vintage year.

    Raises:
        ValueError: If the input is not an integer or is not a supported year.
    """
    # NOTE: Exact type checking rejects bool, which is a subclass of int.
    if type(raw) is not int or raw not in SUPPORTED_YEARS:
        raise ValueError(f"Unsupported study_area_vintage: {raw!r}")

    return raw


def parse_study_area_source_path(raw: object, study_area_type: str) -> Path | None:
    """Parse and validate the study area source from the raw YAML data.

    Args:
        raw (object): The raw data for study area source.
        study_area_type (str): The type of study area.

    Returns:
        Path | None: The source path before root resolution, or None for county mode.

    Raises:
        ValueError: If county mode is selected and a study area source is provided
        ValueError: If the input is not a nonempty string.
        ValueError: If the source path does not have a CSV extension.
    """
    if study_area_type == "county":
        if raw is not None:
            raise ValueError("study_area_source must be null for county mode")

        return None

    source_path = parse_path(raw, "study_area_source")

    if source_path.suffix.lower() != ".csv":
        raise ValueError(f"study_area_source must be a CSV path: {source_path}")

    return source_path


def parse_path(raw: object, field_name: str) -> Path:
    """Parse a nonempty YAML path string without accessing the filesystem.

    Args:
        raw (object): The path value loaded from YAML.
        field_name (str): The setting name to include in validation errors.

    Returns:
        Path: The path as written, without root resolution or tilde expansion.

    Raises:
        ValueError: If the value is not a nonempty string.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field_name} must be a nonempty path string")

    return Path(raw)


def parse_study_area_label(raw: object) -> str:
    """Parse an explicit study-area label independent of the source filename.

    Args:
        raw (object): The label loaded from YAML.

    Returns:
        str: A label containing letters, digits, underscores, or hyphens.

    Raises:
        ValueError: If the label is empty, has an invalid character, or starts with punctuation.
    """
    # NOTE: This regex allows only A-Z, a-z, and 0-9 as the first character of the label, and
    # allows A-Z, a-z, 0-9, underscore, and hyphen for the rest of the label.
    if not isinstance(raw, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", raw):
        raise ValueError(
            "study_area_label must start with a letter or digit and contain only "
            "letters, digits, underscores, or hyphens"
        )

    return raw


def parse_parallel_graph_workers(raw: object) -> int:
    """Parse the process count for parallel graph construction.

    Args:
        raw (object): The worker count loaded from YAML.

    Returns:
        int: A positive number of worker processes.

    Raises:
        ValueError: If the value is not a positive integer, including booleans.
    """
    if type(raw) is not int or raw < 1:
        raise ValueError("parallel_graph_workers must be a positive integer")

    return raw


def resolve_config(settings: PipelineSettings, config_path: Path) -> ResolvedConfig:
    """Resolve configured paths and check the explicitly selected delineation CSV.

    Args:
        settings (PipelineSettings): The parsed pipeline settings.
        config_path (Path): The YAML file whose location anchors repo_root.

    Returns:
        ResolvedConfig: A dataclass containing the resolved configuration values.

    Raises:
        ValueError: If the source path contradicts the study-area mode.
        FileNotFoundError: If the required source path does not refer to a file.
    """
    resolved_config_path = config_path.resolve()
    resolved_root_path = (
        resolved_config_path.parents[1]
        if settings.repo_root_path is None
        else (resolved_config_path.parent / settings.repo_root_path).resolve()
    )
    study_area_source_path = settings.study_area_source_path

    if settings.study_area_type == "county":
        if study_area_source_path is not None:
            raise ValueError("study_area_source must be null for county mode")
    else:
        if study_area_source_path is None:
            raise ValueError("study_area_source must be provided for non-county modes")

        study_area_source_path = (resolved_root_path / study_area_source_path).resolve()

        if not study_area_source_path.is_file():
            raise FileNotFoundError(
                f"study_area_source file does not exist: {study_area_source_path}"
            )

    return ResolvedConfig(
        settings=settings,
        repo_root_path=resolved_root_path,
        data_root_path=(resolved_root_path / settings.data_root_path).resolve(),
        output_root_path=(resolved_root_path / settings.output_root_path).resolve(),
        figure_root_path=(resolved_root_path / settings.figure_root_path).resolve(),
        env_file_path=(resolved_root_path / settings.env_file_path).resolve(),
        study_area_source_path=study_area_source_path,
    )


def build_geography_requests(config: ResolvedConfig) -> tuple[GeographyRequest, ...]:
    """Collect node and definition inputs, preserving order and removing duplicates.

    Args:
        config (ResolvedConfig): The configuration shared by source-preparation stages.

    Returns:
        tuple[GeographyRequest, ...]: Node inputs followed by definition counties and, for
            max-city mode, places at the definition year.
    """
    requests = [
        GeographyRequest(year=year, geography=config.settings.census_geography_type)
        for year in config.effective_years
    ]

    definition_year = config.settings.study_area_vintage
    requests.append(GeographyRequest(year=definition_year, geography="counties"))

    if config.settings.study_area_type == "max_city":
        requests.append(GeographyRequest(year=definition_year, geography="places"))

    return tuple(dict.fromkeys(requests))
