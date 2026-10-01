import re
from enum import Enum

from pydantic import AwareDatetime, BaseModel, Field, HttpUrl, field_validator


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
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: ResourceCategory
    address: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    phone: str | None = None
    website: HttpUrl | None = None
    hours: dict[int, list[tuple[str, str]]] = Field(default_factory=dict)
    availability: Availability = Availability.UNKNOWN
    source_name: str = Field(min_length=1)
    source_url: HttpUrl
    verified_at: AwareDatetime
    # Missing provenance must never promote a record into the production directory.
    is_sample: bool = True

    @field_validator("id", "name", "address", "source_name")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("resource text must not be blank")
        return value

    @field_validator("hours")
    @classmethod
    def valid_weekly_hours(cls, value: dict[int, list[tuple[str, str]]]):
        for day, intervals in value.items():
            if day not in range(7):
                raise ValueError("hours weekdays must be 0 (Monday) through 6 (Sunday)")
            for start, end in intervals:
                if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", start):
                    raise ValueError("hours start must be HH:MM from 00:00 through 23:59")
                if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]|24:00", end):
                    raise ValueError("hours end must be HH:MM; 24:00 is allowed")
                if start >= end:
                    raise ValueError("hours must end after start; split overnight hours by weekday")
        return value


class ResourceResult(BaseModel):
    resource: Resource
    distance_miles: float
    open_now: bool
    availability: Availability
    data_freshness: str
