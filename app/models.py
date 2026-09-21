from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class ResourceCategory(str, Enum):
    SHELTER = "shelter"
    MEAL = "meal"
    WARMING = "warming"
    SHOWER = "shower"


class Availability(str, Enum):
    AVAILABLE = "available"
    FULL = "full"
    UNKNOWN = "unknown"


class Resource(BaseModel):
    id: str
    name: str
    category: ResourceCategory
    address: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    phone: str | None = None
    website: HttpUrl | None = None
    hours: dict[int, list[tuple[str, str]]] = Field(default_factory=dict)
    availability: Availability = Availability.UNKNOWN
    source_name: str
    source_url: HttpUrl
    verified_at: datetime
    is_sample: bool = False


class ResourceResult(BaseModel):
    resource: Resource
    distance_miles: float
    open_now: bool
