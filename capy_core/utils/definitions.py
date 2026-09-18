from typing import Dict, List, Optional

import geopandas as gpd
import pydantic
from pydantic import ConfigDict
from shapely.geometry import Polygon


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
