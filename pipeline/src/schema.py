"""Schema validation for Course JSON data and Courses Index contract."""

from __future__ import annotations

from typing import Any, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class Point2D(BaseModel):
    model_config = ConfigDict(extra="allow")
    x: float
    y: float


class HolePinTee(BaseModel):
    model_config = ConfigDict(extra="allow")
    hole_up: Point2D
    north: Point2D


class HolePathSet(BaseModel):
    model_config = ConfigDict(extra="allow")
    turf: str = ""
    green: str = ""
    fairways: List[str] = Field(default_factory=list)
    tees: List[str] = Field(default_factory=list)
    centerline: str = ""


class HolePaths(BaseModel):
    model_config = ConfigDict(extra="allow")
    hole_up: HolePathSet
    north: HolePathSet


class HazardItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = ""
    name: Optional[str] = ""
    type: Optional[str] = "hazard"
    dist_tee: Optional[float] = 0.0
    dist_pin: Optional[float] = 0.0
    path_hole_up: str = ""
    path_north: str = ""


class HoleData(BaseModel):
    model_config = ConfigDict(extra="allow")
    number: int
    name: str = ""
    par: int
    handicap: Optional[Union[int, str]] = None
    length_yards: Union[int, float]
    rotation_deg: float = 0.0
    bounds_hole_up: List[float] = Field(min_length=4, max_length=4)
    bounds_north: List[float] = Field(min_length=4, max_length=4)
    pin: HolePinTee
    tee: HolePinTee
    paths: HolePaths
    bunkers: List[HazardItem] = Field(default_factory=list)
    waters: List[HazardItem] = Field(default_factory=list)


class OverviewElement(BaseModel):
    model_config = ConfigDict(extra="allow")
    hole: int
    name: Optional[str] = None
    path: str = ""
    center: Optional[List[float]] = None


class OverviewLabel(BaseModel):
    model_config = ConfigDict(extra="allow")
    hole: int
    x: float
    y: float
    name: str = ""
    par: int
    yards: int
    handicap: Union[int, str] = "--"


class CourseOverview(BaseModel):
    model_config = ConfigDict(extra="allow")
    bounds: List[float] = Field(min_length=4, max_length=4)
    turf_path: str = ""
    fairways: List[OverviewElement] = Field(default_factory=list)
    greens: List[OverviewElement] = Field(default_factory=list)
    tees: List[OverviewElement] = Field(default_factory=list)
    bunkers: List[OverviewElement] = Field(default_factory=list)
    waters: List[OverviewElement] = Field(default_factory=list)
    centerlines: List[OverviewElement] = Field(default_factory=list)
    labels: List[OverviewLabel] = Field(default_factory=list)


class CourseData(BaseModel):
    model_config = ConfigDict(extra="allow")
    course_name: str
    total_holes: int
    total_par: int
    total_yards: int
    overview: CourseOverview
    holes: List[HoleData]


class DataAttribution(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = "OpenStreetMap contributors"
    url: str = "https://www.openstreetmap.org/copyright"
    license: str = "ODbL 1.0"


class CourseIndexEntry(BaseModel):
    model_config = ConfigDict(extra="allow")
    slug: str
    name: str
    holes: int
    par: int
    yards: int
    tournaments: List[str] = Field(default_factory=list)
    data_file: str


class CoursesIndex(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: str = "1.0.0"
    generated_at: str
    data_attribution: DataAttribution = Field(default_factory=DataAttribution)
    courses: List[CourseIndexEntry]


def validate_course_data(data: dict[str, Any]) -> CourseData:
    """Validate a serialized course dictionary against CourseData schema."""
    return CourseData.model_validate(data)


def validate_courses_index(data: dict[str, Any]) -> CoursesIndex:
    """Validate a courses index dictionary against CoursesIndex schema."""
    return CoursesIndex.model_validate(data)
