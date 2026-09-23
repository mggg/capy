import json

import geopandas as gpd
from shapely.geometry import Polygon

from capy_core.preprocessing.study_areas import build_county_definitions, fetch_metro_areas


def test_metro_csv_preserves_codes_and_excludes_micropolitan_rows(tmp_path):
    path = tmp_path / "delineation.csv"
    path.write_text(
        "CBSA Code,CBSA Title,Metropolitan/Micropolitan Statistical Area,"
        "FIPS State Code,FIPS County Code\n"
        "10000,Example,Metropolitan Statistical Area,01,001\n"
        "20000,Other,Micropolitan Statistical Area,02,003\n"
    )
    rows = fetch_metro_areas(path)
    assert rows["CBSA Code"].tolist() == ["10000"]
    assert rows["FIPS State Code"].tolist() == ["01"]
    assert rows["FIPS County Code"].tolist() == ["001"]


def test_build_county_definitions(tmp_path):
    source = tmp_path / "2020_counties.shp"
    output_dir = tmp_path / "definitions"
    counties = gpd.GeoDataFrame(
        {
            "STATEFP": ["06"],
            "COUNTYFP": ["037"],
            "NAMELSAD": ["Los Angeles County"],
            "TOTPOP": [100],
        },
        geometry=[
            Polygon(
                [
                    (0, 0),
                    (1, 0),
                    (1, 1),
                    (0, 1),
                    (0, 0),
                ]
            )
        ],
        crs="EPSG:4326",
    )
    counties.to_file(source)

    build_county_definitions(str(source), str(output_dir), "2020")

    definition_json = output_dir / "county_06037_2020.json"
    definition_gpkg = output_dir / "county_06037_2020.gpkg"
    assert definition_json.exists()
    assert definition_gpkg.exists()

    data = json.loads(definition_json.read_text())
    assert data["area_code"] == "06037"
    assert data["area_title"] == "Los Angeles County"
    assert data["component_counties_fips"] == ["06037"]
    assert data["total_population"] == 100
