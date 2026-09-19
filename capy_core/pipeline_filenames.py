"""Translate study-area and census-geography identities to and from pipeline filenames."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from capy_core.pipeline_config import (
    CENSUS_GEOGRAPHY_TYPES,
    STUDY_AREA_TYPES,
    SUPPORTED_YEARS,
    CensusGeographyType,
    StudyAreaType,
    parse_study_area_label,
)


@dataclass(frozen=True, slots=True)
class StudyAreaIdentity:
    """Identify a study-area definition independently of its directory or file extension.

    Attributes:
        study_area_type (StudyAreaType): How the enclosing study area was selected.
        area_code (str): Numeric identifier, retaining any leading zeros.
        study_area_label (str): Explicit definition label, independent of its boundary year.
    """

    study_area_type: StudyAreaType
    area_code: str
    study_area_label: str


@dataclass(frozen=True, slots=True)
class GeographyFileIdentity:
    """Identify census units selected within a study area, or a graph built from those units.

    Attributes:
        study_area (StudyAreaIdentity): The enclosing study-area definition.
        census_geography_type (CensusGeographyType): Geography level of the selected units.
        census_year (int): Year of the census boundaries and populations being analyzed.
    """

    study_area: StudyAreaIdentity
    census_geography_type: CensusGeographyType
    census_year: int


def parse_definition_name(path: str | Path) -> StudyAreaIdentity:
    """Parse a definition JSON/GPKG basename without reading the file.

    Args:
        path (str | Path): Definition filename, optionally including its directory.

    Returns:
        StudyAreaIdentity: The type, code, and complete study-area label.

    Raises:
        ValueError: If the basename does not follow the definition naming grammar.
    """
    filename = Path(path)
    if filename.suffix not in {".json", ".gpkg"}:
        raise ValueError(f"Invalid study-area definition filename: {filename.name}")

    study_area_type, area_code, label = split_study_area_stem(filename.stem)
    identity = StudyAreaIdentity(study_area_type, area_code, label)
    validate_study_area_identity(identity)
    return identity


def split_study_area_stem(stem: str) -> tuple[StudyAreaType, str, str]:
    """Separate the known study-area prefix and code, preserving the remaining text intact.

    Args:
        stem (str): A study-area definition filename stem, without its directory or extension.

    Returns:
        tuple[StudyAreaType, str, str]: The study-area type, code, and remaining label.
    """
    for study_area_type in STUDY_AREA_TYPES:
        prefix = f"{study_area_type}_"
        if not stem.startswith(prefix):
            continue

        area_code, separator, remainder = stem.removeprefix(prefix).partition("_")
        if not separator:
            raise ValueError(f"Missing fields in study-area filename stem: {stem}")

        return cast(StudyAreaType, study_area_type), area_code, remainder

    raise ValueError(f"Unsupported study-area type in filename stem: {stem}")


def format_definition_stem(identity: StudyAreaIdentity) -> str:
    """Format a definition basename, leaving its directory and extension to the caller.

    Args:
        identity (StudyAreaIdentity): The study-area definition to name.

    Returns:
        str: A stem of the form <type>_<code>_<study_area_label>.

    Raises:
        ValueError: If the type, code, or label is invalid.
    """
    validate_study_area_identity(identity)
    return f"{identity.study_area_type}_{identity.area_code}_{identity.study_area_label}"


def validate_study_area_identity(identity: StudyAreaIdentity) -> None:
    """Reject unsupported types, non-string numeric codes, and invalid output labels."""
    if identity.study_area_type not in STUDY_AREA_TYPES:
        raise ValueError(f"Unsupported study-area type: {identity.study_area_type!r}")
    if (
        not isinstance(identity.area_code, str)
        or not identity.area_code.isascii()
        or not identity.area_code.isdecimal()
    ):
        raise ValueError(f"Study-area code must be a string of digits: {identity.area_code!r}")

    parse_study_area_label(identity.study_area_label)


def parse_geography_name(path: str | Path) -> GeographyFileIdentity:
    """Parse a selected-geography GPKG or an original/connected graph JSON basename.

    Args:
        path (str | Path): Geography or graph filename, optionally including its directory.

    Returns:
        GeographyFileIdentity: The geography level, census year, and study-area identity.

    Raises:
        ValueError: If the basename or census year is unsupported.
    """
    name = Path(path).name
    for suffix in ("_vintage.gpkg", "_vintage_orig.json", "_vintage_connected.json"):
        if name.endswith(suffix):
            stem = name.removesuffix(suffix)
            break
    else:
        raise ValueError(f"Invalid geography filename: {name}")

    geography_type, separator, study_area_stem = stem.partition("_in_")
    if not separator or geography_type not in CENSUS_GEOGRAPHY_TYPES:
        raise ValueError(f"Unsupported census geography in filename: {name}")

    study_area_type, area_code, remainder = split_study_area_stem(study_area_stem)
    year, _, label = remainder.partition("_")
    if len(year) != 4 or not year.isascii() or not year.isdecimal():
        raise ValueError(f"Invalid census year in {name}: {year!r}")

    census_year = int(year)
    if census_year not in SUPPORTED_YEARS:
        raise ValueError(f"Unsupported census year in {name}: {census_year}")

    study_area = StudyAreaIdentity(study_area_type, area_code, label)
    validate_study_area_identity(study_area)
    return GeographyFileIdentity(study_area, cast(CensusGeographyType, geography_type), census_year)


def format_geography_stem(geography_identity: GeographyFileIdentity) -> str:
    """Format a census-geography basename shared by selected units and their graphs.

    Args:
        geography_identity (GeographyFileIdentity): The geography and study-area identity to name.

    Returns:
        str: A stem ending in <census_year>_<study_area_label>_vintage.

    Raises:
        ValueError: If the geography, year, or study-area identity is invalid.
    """
    if geography_identity.census_geography_type not in CENSUS_GEOGRAPHY_TYPES:
        raise ValueError(
            f"Unsupported census geography: {geography_identity.census_geography_type!r}"
        )
    if (
        type(geography_identity.census_year) is not int
        or geography_identity.census_year not in SUPPORTED_YEARS
    ):
        raise ValueError(f"Unsupported census year: {geography_identity.census_year!r}")

    identity = geography_identity.study_area
    validate_study_area_identity(identity)
    return (
        f"{geography_identity.census_geography_type}_in_"
        f"{identity.study_area_type}_{identity.area_code}_"
        f"{geography_identity.census_year}_{identity.study_area_label}_vintage"
    )


def format_graph_name(
    geography_identity: GeographyFileIdentity, variant: Literal["orig", "connected"]
) -> str:
    """Format a graph JSON filename with an explicit graph variant.

    Args:
        geography_identity (GeographyFileIdentity): The geography and study-area identity to name.
        variant (Literal["orig", "connected"]): Whether the graph has been connected.

    Returns:
        str: The complete graph basename, including its .json extension.

    Raises:
        ValueError: If the variant or geography identity is invalid.
    """
    if variant not in {"orig", "connected"}:
        raise ValueError(f"Unsupported graph variant: {variant!r}")

    return f"{format_geography_stem(geography_identity)}_{variant}.json"
