"""Build raw input definitions and select files by their configured destination paths."""

import fnmatch

from national_pipeline.geography_types import GeographyLevel, GeographySelection, StudyAreaType
from national_pipeline.pipeline_config import PipelineConfig, select_graph_node_geographies
from national_pipeline.retrieve_data.raw_file_requests import RawFileRequest

from .census.build_requests import build_census_file_requests
from .nhgis.build_requests import build_nhgis_file_requests


def build_raw_file_requests(config: PipelineConfig) -> list[RawFileRequest]:
    """List the population, boundary, and supporting files needed by the configured run.

    Edit the Census or NHGIS builders in this package to change variables, source coverage, URLs,
    or extracts. Choose the run's geography levels and years in YAML.

    Args:
        config (PipelineConfig): Geography levels and years, study areas, and raw-data folders.
            File-path patterns are applied separately by select_raw_file_requests().

    Returns:
        list[RawFileRequest]: Files to retrieve, sorted by their destination filenames. Includes
            county and city data needed to define the study areas, even if not selected as nodes.

    Raises:
        ValueError: Node selections have no supported boundaries or the study-area vintage is
            unsupported for max_city.
    """
    geography_requests = build_geography_requests(config)
    directories = config.raw_data_subdirectories
    requests: list[RawFileRequest] = [
        *build_census_file_requests(directories, geography_requests, config.study_area_type),
        *build_nhgis_file_requests(directories, geography_requests),
    ]
    return sorted(requests, key=lambda request: request.destination_relative_path)


def build_geography_requests(config: PipelineConfig) -> tuple[GeographySelection, ...]:
    """List the years and geography levels needed for graph nodes and their enclosing areas.

    For example, 1990 tracts inside cities defined using 2020 data need four selections:
    1990 tracts, 2020 counties, 2020 places, and 2020 blocks for city population ranking. Population
    and boundary builders receive the same list so they request matching data.

    Args:
        config (PipelineConfig): Requested node levels and years, plus the type and year of the
            enclosing study areas.

    Returns:
        tuple[GeographySelection, ...]: Each needed year/level pair once, sorted by year and level.
            Unsupported 1980 blocks and block groups are left out. County data for the study-area
            year is always included; max_city also needs places and blocks for 2020.

    Raises:
        ValueError: No supported node pairs remain, or max_city uses a vintage other than 2020.
    """
    requests = set(select_graph_node_geographies(config))

    # NOTE: Enclosing study areas use one chosen vintage across all population years, so
    # comparisons do not also switch study-area definitions from decade to decade.
    requests.add(
        GeographySelection(
            census_year=config.study_area_vintage, geography_level=GeographyLevel.COUNTY
        )
    )
    if config.study_area_type == StudyAreaType.MAX_CITY:
        requests.add(
            GeographySelection(
                census_year=config.study_area_vintage, geography_level=GeographyLevel.PLACE
            )
        )

        requests.add(GeographySelection(census_year=2020, geography_level=GeographyLevel.BLOCK))

    return tuple(
        sorted(requests, key=lambda request: (request.census_year, request.geography_level))
    )


def select_raw_file_requests(config: PipelineConfig) -> list[RawFileRequest]:
    """Build this run's raw input requests and apply its destination filename patterns.

    Args:
        config (PipelineConfig): Geography selections, raw folders, and file-path patterns.

    Returns:
        list[RawFileRequest]: Selected downloads in destination order.

    Raises:
        ValueError: Geography selections are unsupported or a pattern matches no request.
    """
    requests = build_raw_file_requests(config)

    return filter_raw_file_requests(requests, config.file_path_patterns)


def filter_raw_file_requests(
    requests: list[RawFileRequest],
    file_path_patterns: tuple[str, ...],
) -> list[RawFileRequest]:
    """Select raw-file requests by destination, retaining their definition order.

    Args:
        requests (list[RawFileRequest]): Input definitions with unique destinations.
        file_path_patterns (tuple[str, ...]): Exact or case-sensitive wildcard destination paths.

    Returns:
        list[RawFileRequest]: Nonempty selection; each pattern must match at least one file.

    Raises:
        ValueError: Destinations repeat, the input list is empty, or selection finds no files.
    """
    destinations = [request.destination_relative_path for request in requests]
    if not destinations or len(set(destinations)) != len(destinations):
        raise ValueError("Raw-file requests must be nonempty and have unique destinations")

    for pattern in file_path_patterns:
        if not any(fnmatch.fnmatchcase(destination, pattern) for destination in destinations):
            raise ValueError(f"No defined files match: {pattern}")

    selected_requests = [
        request
        for request in requests
        if any(
            fnmatch.fnmatchcase(request.destination_relative_path, pattern)
            for pattern in file_path_patterns
        )
    ]
    if not selected_requests:
        raise ValueError("Configuration selects no files")

    return selected_requests
