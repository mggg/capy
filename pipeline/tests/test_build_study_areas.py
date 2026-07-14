import json

import geopandas as gpd
from shapely.geometry import Polygon

from pipeline.build.build_study_areas import build_county_definitions


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
    definition_shp = output_dir / "county_06037_2020.shp"
    assert definition_json.exists()
    assert definition_shp.exists()

    data = json.loads(definition_json.read_text())
    assert data["cbsa_code"] == "06037"
    assert data["cbsa_title"] == "Los Angeles County"
    assert data["component_counties_fips"] == ["06037"]
    assert data["total_population"] == 100
