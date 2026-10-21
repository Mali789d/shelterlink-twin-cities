from typing import Protocol

from .zip_centroids import TWIN_CITIES_ZIP_CENTROIDS


class Geocoder(Protocol):
    def geocode(self, location: str) -> tuple[float, float] | None: ...


class DevelopmentGeocoder:
    """Deterministic local map for development; replace before launch.

    Every Minneapolis (554xx) and Saint Paul (551xx) ZIP resolves to an
    approximate centroid - never an exact address - plus the two city names.
    """

    locations = {
        **TWIN_CITIES_ZIP_CENTROIDS,
        "minneapolis": (44.9778, -93.2650),
        "saint paul": (44.9537, -93.0900),
        "st paul": (44.9537, -93.0900),
    }

    def geocode(self, location: str) -> tuple[float, float] | None:
        return self.locations.get(location.lower().strip())
