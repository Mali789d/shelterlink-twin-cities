from typing import Protocol


class Geocoder(Protocol):
    def geocode(self, location: str) -> tuple[float, float] | None: ...


class DevelopmentGeocoder:
    """Small deterministic map for local development; replace before launch."""

    locations = {
        "55415": (44.9753, -93.2581),
        "55404": (44.9635, -93.2681),
        "55101": (44.9477, -93.0900),
        "minneapolis": (44.9778, -93.2650),
        "saint paul": (44.9537, -93.0900),
        "st paul": (44.9537, -93.0900),
    }

    def geocode(self, location: str) -> tuple[float, float] | None:
        return self.locations.get(location.lower().strip())
