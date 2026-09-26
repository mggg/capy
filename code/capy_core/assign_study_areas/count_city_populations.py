"""Count 2020 block populations inside Census places and their constituent counties."""

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from tqdm import tqdm

from capy_core.geography_types import GeographyLevel
from capy_core.join_geographies.join_population import check_population_join_input
from capy_core.join_geographies.select_inputs import GeographyJoinInputs
from capy_core.population_table_columns import GeographyColumn, PopulationColumn

from .study_area_columns import SelectionColumn, StudyAreaColumn


def count_2020_city_populations_by_county(
    places_df: gpd.GeoDataFrame,
    block_geography_inputs: GeographyJoinInputs,
    raw_data_directory: Path,
    population_table_directory: Path,
) -> pd.DataFrame:
    """Read one state's block points at a time and reconcile candidate-place population totals.

    These are the Census internal points saved in TIGER, not newly calculated polygon points.
    Every block's ID and population must agree with its processed Census population record.
    Blocks outside the candidate places remain outside the city-ranking counts.

    Args:
        places_df (gpd.GeoDataFrame): Unique candidate places with 2020 population and geometry.
        block_geography_inputs (GeographyJoinInputs): 2020 block archive and population paths
            by state.
        raw_data_directory (Path): Configured raw input root.
        population_table_directory (Path): Configured processed population root.

    Returns:
        pd.DataFrame: place_code, county_code, and block_population for each assigned pair.

    Raises:
        OSError: A required archive or population table cannot be read.
        ValueError: Points, identities, block counts, or complete city totals disagree.
    """
    if (
        block_geography_inputs.census_year != 2020
        or block_geography_inputs.geography_level != GeographyLevel.BLOCK
    ):
        raise ValueError("City ranking requires 2020 Census blocks")

    if places_df.empty:
        raise ValueError("City ranking requires positive-area candidate places")

    state_city_county_population_tables = []

    for state_code, state_places_df in tqdm(
        places_df.groupby(GeographyColumn.STATE_CODE, sort=True),
        desc="City population by state",
        unit="state",
        disable=None,
    ):
        state_code = str(state_code)

        if (
            state_code not in block_geography_inputs.population_paths_by_state
            or state_code not in block_geography_inputs.boundary_paths_by_state
        ):
            raise ValueError(f"City ranking lacks 2020 block inputs for state {state_code}")

        block_boundary_archive_path = (
            raw_data_directory / block_geography_inputs.boundary_paths_by_state[state_code]
        )
        block_population_path = (
            population_table_directory
            / block_geography_inputs.population_paths_by_state[state_code]
        )
        block_population_df = pd.read_parquet(block_population_path)
        check_population_join_input(block_population_df, 2020, GeographyLevel.BLOCK, state_code)
        block_internal_points_df = read_2020_block_internal_points(
            block_boundary_archive_path, block_population_df
        )
        state_city_county_population_tables.append(
            assign_block_populations_to_places(
                block_internal_points_df, gpd.GeoDataFrame(state_places_df, crs=places_df.crs)
            )
        )

    city_county_populations_df = pd.concat(state_city_county_population_tables, ignore_index=True)
    block_population_by_place = pd.Series(
        city_county_populations_df.groupby(SelectionColumn.PLACE_ID)[
            SelectionColumn.BLOCK_POPULATION
        ].sum()
    )
    place_ids = pd.Series(places_df[GeographyColumn.GEOGRAPHIC_ID])
    city_populations_from_blocks = place_ids.map(block_population_by_place).fillna(0)
    mismatched_place_ids = places_df.loc[
        city_populations_from_blocks.ne(places_df[PopulationColumn.TOTAL]),
        GeographyColumn.GEOGRAPHIC_ID,
    ]

    if not mismatched_place_ids.empty:
        raise ValueError(
            f"Block populations disagree with whole-city totals: {mismatched_place_ids.tolist()}"
        )

    return city_county_populations_df.sort_values(
        [SelectionColumn.PLACE_ID, StudyAreaColumn.COUNTY_ID]
    ).reset_index(drop=True)


def read_2020_block_internal_points(
    block_boundary_archive_path: Path,
    block_population_df: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """Read TIGER's block points and require complete agreement with processed block populations.

    Args:
        block_boundary_archive_path (Path): Original 2020 state block ZIP.
        block_population_df (pd.DataFrame): Validated 2020 block population table for that state.

    Returns:
        gpd.GeoDataFrame: block_code, county_code, block_population, and NAD83 point geometry.

    Raises:
        OSError: The archive cannot be read; GDAL reader exceptions also propagate.
        ValueError: IDs, internal points, or populations are missing, invalid, or inconsistent.
    """
    archive_address = f"/vsizip/{block_boundary_archive_path.resolve()}"
    layers = pyogrio.list_layers(archive_address)

    if len(layers) != 1:
        raise ValueError("2020 block archive must contain one layer")

    blocks_df = pyogrio.read_dataframe(
        archive_address,
        layer=layers[0][0],
        read_geometry=False,
        columns=["GEOID20", "COUNTYFP20", "POP20", "INTPTLAT20", "INTPTLON20"],
    )
    required_columns = {"GEOID20", "COUNTYFP20", "POP20", "INTPTLAT20", "INTPTLON20"}

    if not required_columns.issubset(blocks_df):
        raise ValueError("2020 block archive lacks population or internal-point fields")

    if (
        blocks_df.GEOID20.duplicated().any()
        or not blocks_df.GEOID20.str.fullmatch(r"[0-9]{15}", na=False).all()
        or set(blocks_df.GEOID20) != set(block_population_df[GeographyColumn.GEOGRAPHIC_ID])
        or not blocks_df.COUNTYFP20.eq(blocks_df.GEOID20.str[2:5]).all()
    ):
        raise ValueError("2020 TIGER blocks disagree with processed block identities")

    processed_block_populations = block_population_df.set_index(GeographyColumn.GEOGRAPHIC_ID)[
        PopulationColumn.TOTAL
    ]

    if not blocks_df.POP20.eq(blocks_df.GEOID20.map(processed_block_populations)).all():
        raise ValueError("2020 TIGER block populations disagree with processed Census counts")

    latitudes = pd.Series(pd.to_numeric(blocks_df.INTPTLAT20, errors="raise"))
    longitudes = pd.Series(pd.to_numeric(blocks_df.INTPTLON20, errors="raise"))

    if not latitudes.between(-90, 90).all() or not longitudes.between(-180, 180).all():
        raise ValueError("2020 block internal points must be valid latitude/longitude pairs")

    return gpd.GeoDataFrame(
        {
            SelectionColumn.BLOCK_ID: blocks_df.GEOID20,
            StudyAreaColumn.COUNTY_ID: blocks_df.GEOID20.str[:5],
            SelectionColumn.BLOCK_POPULATION: blocks_df.POP20,
        },
        geometry=gpd.points_from_xy(longitudes, latitudes),
        crs="EPSG:4269",
    )


def assign_block_populations_to_places(
    block_internal_points_df: gpd.GeoDataFrame,
    places_df: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Sum blocks whose Census internal point lies strictly inside each candidate place.

    Args:
        block_internal_points_df (gpd.GeoDataFrame): Unique block points with county codes
            and populations.
        places_df (gpd.GeoDataFrame): Candidate-place boundaries with unique GEOIDs.

    Returns:
        pd.DataFrame: Population by place_code and county_code. Input tables are unchanged.

    Raises:
        ValueError: A block is assigned to more than one place.
    """
    if block_internal_points_df.crs is None:
        raise ValueError("Block internal points need a coordinate reference system")

    place_boundaries_df = places_df.rename(
        columns={GeographyColumn.GEOGRAPHIC_ID: SelectionColumn.PLACE_ID}
    )
    place_boundaries_df = gpd.GeoDataFrame(
        place_boundaries_df[[SelectionColumn.PLACE_ID, "geometry"]], crs=places_df.crs
    ).to_crs(block_internal_points_df.crs)
    assigned_blocks_df = gpd.sjoin(
        block_internal_points_df, place_boundaries_df, how="inner", predicate="within"
    )

    if assigned_blocks_df[SelectionColumn.BLOCK_ID].duplicated().any():
        raise ValueError("A Census block internal point lies in more than one candidate place")

    return pd.DataFrame(
        assigned_blocks_df.groupby(
            [SelectionColumn.PLACE_ID, StudyAreaColumn.COUNTY_ID], as_index=False
        )[[SelectionColumn.BLOCK_POPULATION]].sum()
    )
