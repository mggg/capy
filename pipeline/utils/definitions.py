import pydantic
import geopandas as gpd
from shapely.geometry import Polygon
from typing import List, Optional, Dict


class StudyArea(pydantic.BaseModel):
    class Config:
        arbitrary_types_allowed = True

    area_code: str
    area_title: str
    component_counties_fips: List[str]
    total_population: Optional[int] = None
    geometry: Optional[gpd.GeoDataFrame] = None


if hasattr(pydantic, "RootModel"):
    class StudyAreaDict(pydantic.RootModel[Dict[str, StudyArea]]):
        pass
else:
    class StudyAreaDict(pydantic.BaseModel):
        __root__: Dict[str, StudyArea]
