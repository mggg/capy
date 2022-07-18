import pydantic
import geopandas as gpd
from shapely.geometry import Polygon
from typing import List, Optional, Dict


class CBSA(pydantic.BaseModel):
    class Config:
        arbitrary_types_allowed = True

    cbsa_code: str
    cbsa_title: str
    component_counties_fips: List[str]
    total_population: Optional[int]
    geometry: Optional[gpd.GeoDataFrame]


class CBSADict(pydantic.BaseModel):
    __root__: Dict[str, CBSA]
