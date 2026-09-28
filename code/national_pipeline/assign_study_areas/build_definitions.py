"""Construct county and metro definitions and rank their county or city candidates."""

from enum import StrEnum
from pathlib import Path

import geopandas as gpd
import pandas as pd

from national_pipeline.geography_types import StudyAreaType
from national_pipeline.population_table_columns import GeographyColumn, PopulationColumn
from national_pipeline.retrieve_data.census.table_columns import CensusGeographyColumn

from .study_area_columns import SelectionColumn, StudyAreaColumn


class SelectionReason(StrEnum):
    """Recorded reasons for a county/metro definition or a city candidate's ranking outcome."""

    COUNTY_SELECTED = "selected_county"
    ALL_METRO_COUNTIES = "all_metro_counties"
    MAXIMUM_COUNTY_POPULATION = "greatest_county_population_smallest_code_breaks_ties"
    LOWER_CITY_POPULATION_INSIDE_METRO = "lower_population_inside_metro"
    MAXIMUM_CITY_POPULATION_INSIDE_METRO = "greatest_population_inside_metro"
    CITY_POPULATION_TIE = "equal_population_smallest_place_code_wins"


def read_metro_counties(metro_membership_workbook_path: Path) -> pd.DataFrame:
    """Read March 2020 metropolitan county memberships, excluding micropolitan areas.

    Args:
        metro_membership_workbook_path (Path): Original Census delineation workbook.

    Returns:
        pd.DataFrame: metro_code, metro_name, and five-digit county_code, one row per member.

    Raises:
        OSError: The workbook cannot be read.
        ValueError: Required columns, identifiers, names, or unique memberships are missing.
    """
    metro_roster_df = pd.read_excel(metro_membership_workbook_path, skiprows=2, dtype=str)
    required_columns = {
        "CBSA Code",
        "CBSA Title",
        "Metropolitan/Micropolitan Statistical Area",
        "FIPS State Code",
        "FIPS County Code",
    }

    if not required_columns.issubset(metro_roster_df):
        raise ValueError(f"Metro workbook lacks required columns: {metro_membership_workbook_path}")

    metro_roster_df = metro_roster_df.loc[
        metro_roster_df["Metropolitan/Micropolitan Statistical Area"].eq(
            "Metropolitan Statistical Area"
        )
    ].copy()
    metro_counties_df = pd.DataFrame(
        {
            StudyAreaColumn.METRO_CODE: metro_roster_df["CBSA Code"],
            StudyAreaColumn.METRO_NAME: metro_roster_df["CBSA Title"],
            StudyAreaColumn.COUNTY_ID: metro_roster_df["FIPS State Code"]
            + metro_roster_df["FIPS County Code"],
        }
    )

    if metro_counties_df.empty:
        raise ValueError("Metro workbook contains no metropolitan counties")

    for column in (StudyAreaColumn.METRO_CODE, StudyAreaColumn.COUNTY_ID):
        if not metro_counties_df[column].str.fullmatch(r"[0-9]{5}", na=False).all():
            raise ValueError(f"Metro workbook has invalid {column}")

    if (
        metro_counties_df[StudyAreaColumn.COUNTY_ID].duplicated().any()
        or metro_counties_df[StudyAreaColumn.METRO_NAME].fillna("").str.strip().eq("").any()
        or bool(
            metro_counties_df.groupby(StudyAreaColumn.METRO_CODE)[StudyAreaColumn.METRO_NAME]
            .nunique()
            .ne(1)
            .any()
        )
    ):
        raise ValueError("Metro county memberships or names are ambiguous")

    return metro_counties_df.sort_values(
        [StudyAreaColumn.METRO_CODE, StudyAreaColumn.COUNTY_ID]
    ).reset_index(drop=True)


def build_metro_boundaries(
    counties_df: gpd.GeoDataFrame, metro_counties_df: pd.DataFrame
) -> gpd.GeoDataFrame:
    """Combine complete county lists into metro boundaries without changing either input.

    Args:
        counties_df (gpd.GeoDataFrame): Definition-vintage counties with county_code and TOTPOP.
        metro_counties_df (pd.DataFrame): Validated March 2020 membership rows.

    Returns:
        gpd.GeoDataFrame: One boundary, population, and county-code list per metro.

    Raises:
        ValueError: A required county is absent or supplied more than once.
    """
    missing_county_ids = set(metro_counties_df[StudyAreaColumn.COUNTY_ID]) - set(
        counties_df[StudyAreaColumn.COUNTY_ID]
    )

    if missing_county_ids or counties_df[StudyAreaColumn.COUNTY_ID].duplicated().any():
        raise ValueError(
            "Metro definitions require complete, unique counties; "
            f"missing {sorted(missing_county_ids)}"
        )

    metro_county_boundaries_df = metro_counties_df.merge(
        counties_df, on=StudyAreaColumn.COUNTY_ID, validate="many_to_one"
    )
    metro_records = []

    for metro_code, member_counties_df in metro_county_boundaries_df.groupby(
        StudyAreaColumn.METRO_CODE, sort=True
    ):
        metro_records.append(
            {
                StudyAreaColumn.METRO_CODE: metro_code,
                StudyAreaColumn.METRO_NAME: member_counties_df[StudyAreaColumn.METRO_NAME].iloc[0],
                StudyAreaColumn.COUNTY_IDS: sorted(
                    member_counties_df[StudyAreaColumn.COUNTY_ID].tolist()
                ),
                PopulationColumn.TOTAL: int(member_counties_df[PopulationColumn.TOTAL].sum()),
                "geometry": gpd.GeoSeries(
                    member_counties_df.geometry, crs=counties_df.crs
                ).union_all(),
            }
        )

    return gpd.GeoDataFrame(metro_records, crs=counties_df.crs)


def build_city_candidates(places_df: gpd.GeoDataFrame, metros_df: gpd.GeoDataFrame) -> pd.DataFrame:
    """List positive-area place/metro intersections, retaining full-city population and area.

    Args:
        places_df (gpd.GeoDataFrame): Definition-vintage places in a projected metre CRS.
        metros_df (gpd.GeoDataFrame): Metro boundaries in the same CRS.

    Returns:
        pd.DataFrame: Place and metro IDs, names, full population, and overlap/full areas in km².
            Includes Census-designated places; zero-area boundary contacts are excluded.
    """
    city_candidate_records = []

    for _, metro in metros_df.iterrows():
        candidate_place_indexes = places_df.sindex.query(metro.geometry, predicate="intersects")

        for _, place in places_df.iloc[candidate_place_indexes].iterrows():
            overlap_area_square_metres = place.geometry.intersection(metro.geometry).area

            if overlap_area_square_metres <= 0:
                continue

            city_candidate_records.append(
                {
                    StudyAreaColumn.METRO_CODE: metro[StudyAreaColumn.METRO_CODE],
                    StudyAreaColumn.METRO_NAME: metro[StudyAreaColumn.METRO_NAME],
                    SelectionColumn.PLACE_ID: place[GeographyColumn.GEOGRAPHIC_ID],
                    SelectionColumn.PLACE_NAME: place[CensusGeographyColumn.NAME],
                    SelectionColumn.CITY_POPULATION: int(place[PopulationColumn.TOTAL]),
                    SelectionColumn.AREA_INSIDE_METRO_KM2: overlap_area_square_metres / 1_000_000,
                    SelectionColumn.CITY_AREA_KM2: place.geometry.area / 1_000_000,
                }
            )

    return (
        pd.DataFrame(
            city_candidate_records,
            columns=pd.Index(
                [
                    StudyAreaColumn.METRO_CODE,
                    StudyAreaColumn.METRO_NAME,
                    SelectionColumn.PLACE_ID,
                    SelectionColumn.PLACE_NAME,
                    SelectionColumn.CITY_POPULATION,
                    SelectionColumn.AREA_INSIDE_METRO_KM2,
                    SelectionColumn.CITY_AREA_KM2,
                ]
            ),
        )
        .sort_values([StudyAreaColumn.METRO_CODE, SelectionColumn.PLACE_ID])
        .reset_index(drop=True)
    )


def rank_and_select_city_candidates(
    city_candidates_df: pd.DataFrame,
    city_county_populations_df: pd.DataFrame,
    metro_counties_df: pd.DataFrame,
) -> pd.DataFrame:
    """Select the city with the greatest estimated population inside each metro.

    Rank each candidate by the summed population of blocks assigned to both the city and metro.
    Only residents inside that overlap count toward selection; the city's population outside the
    metro does not. The largest positive total wins, with the smallest place GEOID breaking ties.
    All candidates remain in the returned table, with exactly one marked selected per metro.

    Args:
        city_candidates_df (pd.DataFrame): Positive-area candidates with full city populations.
        city_county_populations_df (pd.DataFrame): place_code, county_code, and block_population.
        metro_counties_df (pd.DataFrame): Complete metro/county memberships.

    Returns:
        pd.DataFrame: All candidates with population_inside_metro, selected, and selection_reason.
            Equal positive scores use the smallest place GEOID as a reproducible tie-break.

    Raises:
        ValueError: A metro has no populated candidate, a score exceeds city population, or
            populated city/metro membership lacks positive polygon overlap.
    """
    city_county_populations_with_metros_df = city_county_populations_df.merge(
        metro_counties_df[[StudyAreaColumn.METRO_CODE, StudyAreaColumn.COUNTY_ID]],
        on=StudyAreaColumn.COUNTY_ID,
        validate="many_to_one",
    )
    city_metro_populations_df = pd.DataFrame(
        city_county_populations_with_metros_df.groupby(
            [StudyAreaColumn.METRO_CODE, SelectionColumn.PLACE_ID], as_index=False
        )[[SelectionColumn.BLOCK_POPULATION]].sum()
    )
    city_metro_populations_df = city_metro_populations_df.rename(
        columns={SelectionColumn.BLOCK_POPULATION: SelectionColumn.POPULATION_INSIDE_METRO}
    )
    ranked_city_candidates_df = city_candidates_df.merge(
        city_metro_populations_df,
        how="outer",
        on=[StudyAreaColumn.METRO_CODE, SelectionColumn.PLACE_ID],
        validate="one_to_one",
    )

    if (
        ranked_city_candidates_df.loc[
            ranked_city_candidates_df[SelectionColumn.CITY_POPULATION].isna(),
            SelectionColumn.POPULATION_INSIDE_METRO,
        ]
        .gt(0)
        .any()
    ):
        raise ValueError("Populated city/metro assignment lacks positive polygon overlap")

    ranked_city_candidates_df = ranked_city_candidates_df.loc[
        ranked_city_candidates_df[SelectionColumn.CITY_POPULATION].notna()
    ].copy()
    ranked_city_candidates_df[SelectionColumn.CITY_POPULATION] = ranked_city_candidates_df[
        SelectionColumn.CITY_POPULATION
    ].astype("int64")
    ranked_city_candidates_df[SelectionColumn.POPULATION_INSIDE_METRO] = (
        ranked_city_candidates_df[SelectionColumn.POPULATION_INSIDE_METRO].fillna(0).astype("int64")
    )

    if (
        ranked_city_candidates_df[SelectionColumn.POPULATION_INSIDE_METRO]
        .gt(ranked_city_candidates_df[SelectionColumn.CITY_POPULATION])
        .any()
    ):
        raise ValueError("Population inside metro exceeds the whole-city population")

    ranked_city_candidates_df = ranked_city_candidates_df.sort_values(
        [
            StudyAreaColumn.METRO_CODE,
            SelectionColumn.POPULATION_INSIDE_METRO,
            SelectionColumn.PLACE_ID,
        ],
        ascending=[True, False, True],
    ).reset_index(drop=True)
    ranked_city_candidates_df[SelectionColumn.SELECTED] = ~ranked_city_candidates_df[
        StudyAreaColumn.METRO_CODE
    ].duplicated()
    selected_city_candidates_df = ranked_city_candidates_df.loc[
        ranked_city_candidates_df[SelectionColumn.SELECTED]
    ]

    if (
        set(selected_city_candidates_df[StudyAreaColumn.METRO_CODE])
        != set(metro_counties_df[StudyAreaColumn.METRO_CODE])
        or selected_city_candidates_df[SelectionColumn.POPULATION_INSIDE_METRO].le(0).any()
    ):
        raise ValueError("Every metro must have a city with positive population inside it")

    ranked_city_candidates_df[SelectionColumn.SELECTION_REASON] = (
        SelectionReason.LOWER_CITY_POPULATION_INSIDE_METRO.value
    )
    ranked_city_candidates_df.loc[
        ranked_city_candidates_df[SelectionColumn.SELECTED], SelectionColumn.SELECTION_REASON
    ] = SelectionReason.MAXIMUM_CITY_POPULATION_INSIDE_METRO.value
    has_maximum_population = ranked_city_candidates_df[SelectionColumn.POPULATION_INSIDE_METRO].eq(
        ranked_city_candidates_df.groupby(StudyAreaColumn.METRO_CODE)[
            SelectionColumn.POPULATION_INSIDE_METRO
        ].transform("max")
    )
    has_population_tie = ranked_city_candidates_df.loc[has_maximum_population][
        StudyAreaColumn.METRO_CODE
    ].duplicated(keep=False)
    tied_metro_codes = ranked_city_candidates_df.loc[has_maximum_population].loc[
        has_population_tie, StudyAreaColumn.METRO_CODE
    ]
    ranked_city_candidates_df.loc[
        ranked_city_candidates_df[StudyAreaColumn.METRO_CODE].isin(tied_metro_codes)
        & has_maximum_population,
        SelectionColumn.SELECTION_REASON,
    ] = SelectionReason.CITY_POPULATION_TIE.value

    return ranked_city_candidates_df


def build_study_area_definitions(
    counties_df: gpd.GeoDataFrame,
    study_area_type: StudyAreaType,
    definition_year: int,
    metros_df: gpd.GeoDataFrame | None = None,
    places_df: gpd.GeoDataFrame | None = None,
    city_candidates_df: pd.DataFrame | None = None,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Build selected whole-area boundaries, keeping metro, county, and place roles distinct.

    Args:
        counties_df (gpd.GeoDataFrame): Counties with county_code, NAME, and study populations.
        study_area_type (StudyAreaType): county, cbsa, max_county, or max_city.
        definition_year (int): Definition vintage, fixed across graph-node years.
        metros_df (gpd.GeoDataFrame | None): Required complete metros for non-county modes.
        places_df (gpd.GeoDataFrame | None): Required 2020 places for max_city.
        city_candidates_df (pd.DataFrame | None): Ranked candidates for max_city.

    Returns:
        tuple[gpd.GeoDataFrame, pd.DataFrame]: Definitions and candidate scores. Metro modes
            identify definitions by their metro code, even if two metros choose the same place.

    Raises:
        ValueError: Inputs for the requested mode are absent or a selected county/city is missing.
    """
    if study_area_type == StudyAreaType.COUNTY:
        selected_areas_df = counties_df.rename(
            columns={
                CensusGeographyColumn.NAME: StudyAreaColumn.NAME,
                PopulationColumn.TOTAL: StudyAreaColumn.DEFINITION_POPULATION,
            }
        ).copy()
        selected_areas_df[StudyAreaColumn.STUDY_AREA_ID] = (
            StudyAreaType.COUNTY.value + "_" + selected_areas_df[StudyAreaColumn.COUNTY_ID]
        )
        selected_areas_df[StudyAreaColumn.COUNTY_IDS] = selected_areas_df[
            StudyAreaColumn.COUNTY_ID
        ].map(lambda county_id: [county_id])
        selected_areas_df[StudyAreaColumn.SELECTED_COUNTY_ID] = selected_areas_df[
            StudyAreaColumn.COUNTY_ID
        ]
        selected_areas_df[StudyAreaColumn.SELECTED_PLACE_ID] = None
        (
            selected_areas_df[StudyAreaColumn.METRO_CODE],
            selected_areas_df[StudyAreaColumn.METRO_NAME],
        ) = None, None
        selected_areas_df[StudyAreaColumn.METRO_COUNTY_IDS] = [
            [] for _ in range(len(selected_areas_df))
        ]
        selected_areas_df[SelectionColumn.SELECTION_REASON] = SelectionReason.COUNTY_SELECTED.value
        selection_candidates_df = pd.DataFrame()
    else:
        if metros_df is None:
            raise ValueError("Metro definitions are required")

        if study_area_type == StudyAreaType.MAX_COUNTY:
            selected_areas_df, selection_candidates_df = select_most_populous_counties(
                counties_df, metros_df
            )
        elif study_area_type == StudyAreaType.MAX_CITY:
            if places_df is None or city_candidates_df is None:
                raise ValueError("City definitions require places and ranked population scores")

            selected_areas_df = build_selected_city_definitions(
                counties_df, places_df, city_candidates_df
            )
            selection_candidates_df = city_candidates_df
        else:
            selected_areas_df = metros_df.rename(
                columns={
                    StudyAreaColumn.METRO_NAME: StudyAreaColumn.NAME,
                    PopulationColumn.TOTAL: StudyAreaColumn.DEFINITION_POPULATION,
                }
            ).copy()
            (
                selected_areas_df[StudyAreaColumn.SELECTED_COUNTY_ID],
                selected_areas_df[StudyAreaColumn.SELECTED_PLACE_ID],
            ) = (
                None,
                None,
            )
            selected_areas_df[SelectionColumn.SELECTION_REASON] = (
                SelectionReason.ALL_METRO_COUNTIES.value
            )
            selection_candidates_df = pd.DataFrame()

        metro_labels_df = pd.DataFrame(
            metros_df[
                [
                    StudyAreaColumn.METRO_CODE,
                    StudyAreaColumn.METRO_NAME,
                    StudyAreaColumn.COUNTY_IDS,
                ]
            ]
        ).rename(columns={StudyAreaColumn.COUNTY_IDS: StudyAreaColumn.METRO_COUNTY_IDS})
        selected_areas_df = selected_areas_df.merge(
            metro_labels_df, on=StudyAreaColumn.METRO_CODE, validate="one_to_one"
        )
        selected_areas_df[StudyAreaColumn.STUDY_AREA_ID] = (
            study_area_type.value + "_" + selected_areas_df[StudyAreaColumn.METRO_CODE]
        )

    selected_areas_df[StudyAreaColumn.STUDY_AREA_TYPE] = study_area_type.value
    selected_areas_df[StudyAreaColumn.DEFINITION_YEAR] = definition_year
    output_columns = [
        StudyAreaColumn.STUDY_AREA_ID,
        StudyAreaColumn.STUDY_AREA_TYPE,
        StudyAreaColumn.DEFINITION_YEAR,
        StudyAreaColumn.NAME,
        StudyAreaColumn.METRO_CODE,
        StudyAreaColumn.METRO_NAME,
        StudyAreaColumn.METRO_COUNTY_IDS,
        StudyAreaColumn.COUNTY_IDS,
        StudyAreaColumn.SELECTED_COUNTY_ID,
        StudyAreaColumn.SELECTED_PLACE_ID,
        StudyAreaColumn.DEFINITION_POPULATION,
        SelectionColumn.SELECTION_REASON,
        "geometry",
    ]
    study_area_definitions_df = gpd.GeoDataFrame(
        selected_areas_df[output_columns], crs=counties_df.crs
    )

    study_area_definitions_df = gpd.GeoDataFrame(
        study_area_definitions_df.sort_values(StudyAreaColumn.STUDY_AREA_ID).reset_index(drop=True),
        crs=counties_df.crs,
    )

    return study_area_definitions_df, selection_candidates_df


def select_most_populous_counties(
    counties_df: gpd.GeoDataFrame,
    metros_df: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Select the county with the greatest total population among each metro's member counties.

    Compare the full population of each county on the metro's membership list. The largest total
    wins, with the smallest five-digit county code breaking ties. Retain the winning county's
    whole boundary and return every candidate's population, with one marked selected per metro.

    Args:
        counties_df (gpd.GeoDataFrame): Complete definition counties with county_code and TOTPOP.
        metros_df (gpd.GeoDataFrame): Complete metros with county_codes lists.

    Returns:
        tuple[gpd.GeoDataFrame, pd.DataFrame]: Selected county definitions and all county scores.
    """
    metro_counties_df = (
        pd.DataFrame(metros_df[[StudyAreaColumn.METRO_CODE, StudyAreaColumn.COUNTY_IDS]])
        .explode(StudyAreaColumn.COUNTY_IDS)
        .rename(columns={StudyAreaColumn.COUNTY_IDS: StudyAreaColumn.COUNTY_ID})
    )
    county_candidates_df = metro_counties_df.merge(
        counties_df, on=StudyAreaColumn.COUNTY_ID, validate="many_to_one"
    ).sort_values(
        [StudyAreaColumn.METRO_CODE, PopulationColumn.TOTAL, StudyAreaColumn.COUNTY_ID],
        ascending=[True, False, True],
    )
    county_candidates_df[SelectionColumn.SELECTED] = ~county_candidates_df[
        StudyAreaColumn.METRO_CODE
    ].duplicated()
    selected_counties_df = (
        county_candidates_df.loc[county_candidates_df[SelectionColumn.SELECTED]]
        .rename(
            columns={
                CensusGeographyColumn.NAME: StudyAreaColumn.NAME,
                PopulationColumn.TOTAL: StudyAreaColumn.DEFINITION_POPULATION,
            }
        )
        .copy()
    )
    selected_counties_df[StudyAreaColumn.COUNTY_IDS] = selected_counties_df[
        StudyAreaColumn.COUNTY_ID
    ].map(lambda county_id: [county_id])
    selected_counties_df[StudyAreaColumn.SELECTED_COUNTY_ID] = selected_counties_df[
        StudyAreaColumn.COUNTY_ID
    ]
    selected_counties_df[StudyAreaColumn.SELECTED_PLACE_ID] = None
    selected_counties_df[SelectionColumn.SELECTION_REASON] = (
        SelectionReason.MAXIMUM_COUNTY_POPULATION.value
    )
    county_scores_df = pd.DataFrame(
        county_candidates_df[
            [
                StudyAreaColumn.METRO_CODE,
                StudyAreaColumn.COUNTY_ID,
                PopulationColumn.TOTAL,
                SelectionColumn.SELECTED,
            ]
        ]
    )

    return gpd.GeoDataFrame(selected_counties_df, crs=counties_df.crs), county_scores_df


def build_selected_city_definitions(
    counties_df: gpd.GeoDataFrame,
    places_df: gpd.GeoDataFrame,
    city_candidates_df: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """Retain each winning city's whole boundary and identify its actual intersecting counties.

    Args:
        counties_df (gpd.GeoDataFrame): Complete definition counties with county_code.
        places_df (gpd.GeoDataFrame): All places, in the same projected CRS as the counties.
        city_candidates_df (pd.DataFrame): Ranked candidates with exactly one selected place
            per metro.

    Returns:
        gpd.GeoDataFrame: Selected cities, including counties outside their selecting metro.
    """
    selected_city_candidates_df = city_candidates_df.loc[
        city_candidates_df[SelectionColumn.SELECTED],
        [StudyAreaColumn.METRO_CODE, SelectionColumn.PLACE_ID, SelectionColumn.SELECTION_REASON],
    ]
    selected_cities_df = selected_city_candidates_df.merge(
        places_df,
        left_on=SelectionColumn.PLACE_ID,
        right_on=GeographyColumn.GEOGRAPHIC_ID,
        validate="many_to_one",
    ).rename(
        columns={
            CensusGeographyColumn.NAME: StudyAreaColumn.NAME,
            PopulationColumn.TOTAL: StudyAreaColumn.DEFINITION_POPULATION,
        }
    )
    selected_city_county_ids = []

    for city_geometry in selected_cities_df.geometry:
        candidate_county_indexes = counties_df.sindex.query(city_geometry, predicate="intersects")
        intersecting_counties_df = counties_df.iloc[candidate_county_indexes]
        has_positive_area_overlap = intersecting_counties_df.geometry.intersection(
            city_geometry
        ).area.gt(0)
        selected_city_county_ids.append(
            intersecting_counties_df.loc[has_positive_area_overlap, StudyAreaColumn.COUNTY_ID]
            .sort_values()
            .tolist()
        )

    selected_cities_df[StudyAreaColumn.COUNTY_IDS] = selected_city_county_ids
    selected_cities_df[StudyAreaColumn.SELECTED_COUNTY_ID] = None
    selected_cities_df[StudyAreaColumn.SELECTED_PLACE_ID] = selected_cities_df[
        SelectionColumn.PLACE_ID
    ]

    return gpd.GeoDataFrame(selected_cities_df, crs=places_df.crs)
