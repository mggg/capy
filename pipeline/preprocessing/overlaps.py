import typer
import tqdm
import glob
import geopandas as gpd
import sys
from pathlib import Path


# for flexibility with different versions of geopandas
def union_geometry(gdf: gpd.GeoDataFrame):
    geometry = gdf.geometry
    if hasattr(geometry, "union_all"):
        return geometry.union_all()
    return geometry.unary_union


def output_stem(
    study_area_file: str,
    prefix: str,
    census_geography_type: str,
    census_geography_year: str,
    definition_vintage: str,
) -> str:
    study_area_stem = Path(study_area_file).stem
    if census_geography_type and census_geography_year and definition_vintage:
        vintage_suffix = f"_{definition_vintage}"
        if not study_area_stem.endswith(vintage_suffix):
            raise ValueError(
                f"{study_area_file} does not end with vintage {definition_vintage}"
            )
        study_area_identity = study_area_stem.removesuffix(vintage_suffix)
        return (
            f"{prefix}{census_geography_type}_in_{study_area_identity}_"
            f"{census_geography_year}_{definition_vintage}_vintage"
        )
    return f"{prefix}{study_area_stem}_geographies"


def main(
    census_geographies_file: str,
    study_area_glob: str,
    output_dir: str,
    prefix: str = "",
    census_geography_type: str = "",
    census_geography_year: str = "",
    definition_vintage: str = "",
):
    """
    Writes census geographies whose representative points fall within each study area.
    """
    census_geographies = gpd.read_file(census_geographies_file)
    geography_points = census_geographies.geometry.representative_point()
    all_geographies_area = union_geometry(census_geographies).area

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    for study_area_file in tqdm.tqdm(sorted(glob.glob(study_area_glob))):
        study_area_gdf = gpd.read_file(study_area_file).to_crs(census_geographies.crs)
        study_area_boundary = union_geometry(study_area_gdf)

        geography_indices = geography_points.sindex.query(
            study_area_boundary, predicate="covers")
        selected_geographies = census_geographies.iloc[sorted(geography_indices)]

        if len(selected_geographies) != 0:
            selected_geographies_stem = output_stem(
                study_area_file,
                prefix,
                census_geography_type,
                census_geography_year,
                definition_vintage,
            )
            selected_geographies.to_file(
                f"{output_dir}/{selected_geographies_stem}.gpkg", driver="GPKG")
        else:
            print(
                "empty overlaps computed:",
                census_geographies_file,
                study_area_file,
                output_dir,
                file=sys.stderr)


if __name__ == "__main__":
    typer.run(main)
