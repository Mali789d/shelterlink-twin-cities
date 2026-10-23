from typing import Protocol

from .zip_centroids import TWIN_CITIES_ZIP_CENTROIDS


class Geocoder(Protocol):
    def geocode(self, location: str) -> tuple[float, float] | None: ...


# City names resolve to the mean of that city's covered ZIP centroids, with the
# city-to-ZIP mapping from the Census-based state/county/ZIP reference
# (scpike/us-state-county-zip) - approximate, never an exact address.
# Minneapolis and Saint Paul keep their downtown coordinates instead, and the
# "st" aliases mirror their "saint" entries.
TWIN_CITIES_CITY_CENTROIDS: dict[str, tuple[float, float]] = {
    "minneapolis": (44.9778, -93.2650),
    "saint paul": (44.9537, -93.0900),
    "st paul": (44.9537, -93.0900),
    "apple valley": (44.739462, -93.193842),
    "blaine": (45.170133, -93.216146),
    "bloomington": (44.831830, -93.308979),
    "brooklyn center": (45.088209, -93.320774),
    "brooklyn park": (45.122441, -93.379184),
    "champlin": (45.172932, -93.386829),
    "columbia heights": (45.050884, -93.253812),
    "coon rapids": (45.177025, -93.307692),
    "crystal": (45.062950, -93.381362),
    "dayton": (45.195735, -93.475802),
    "eagan": (44.834317, -93.161744),
    "eden prairie": (44.871734, -93.447645),
    "edina": (44.894120, -93.349533),
    "excelsior": (44.895664, -93.607649),
    "fridley": (45.096702, -93.253726),
    "golden valley": (45.005499, -93.379150),
    "hamel": (45.078263, -93.572118),
    "lauderdale": (44.982482, -93.174880),
    "little canada": (45.003562, -93.091280),
    "long lake": (44.994245, -93.589620),
    "loretto": (45.103722, -93.674218),
    "maple grove": (45.116924, -93.471214),
    "maple plain": (45.009760, -93.698110),
    "maplewood": (44.937421, -93.007402),
    "mendota": (44.886640, -93.165422),
    "minnetonka": (44.935908, -93.456214),
    "mound": (44.936989, -93.677783),
    "new brighton": (45.081866, -93.190493),
    "north saint paul": (45.014551, -93.025535),
    "oakdale": (44.987546, -92.963553),
    "plymouth": (45.023869, -93.457527),
    "richfield": (44.874460, -93.282529),
    "robbinsdale": (45.009275, -93.341105),
    "rogers": (45.175548, -93.575531),
    "roseville": (45.012196, -93.151186),
    "saint louis park": (44.954251, -93.355210),
    "shoreview": (45.084450, -93.132817),
    "spring park": (44.937621, -93.635153),
    "st louis park": (44.954251, -93.355210),
    "vadnais heights": (45.083907, -93.080233),
    "wayzata": (44.956401, -93.538993),
    "west saint paul": (44.912692, -93.090059),
    "white bear lake": (45.078907, -92.979715),
    "woodbury": (44.918031, -92.938277),
}


class DevelopmentGeocoder:
    """Deterministic local map for development; replace before launch.

    Every covered metro ZIP (Hennepin and Ramsey counties plus metro-adjacent
    ZIPs) and the municipalities those ZIPs belong to resolve to an approximate
    centroid - never an exact address.
    """

    locations = {
        **TWIN_CITIES_ZIP_CENTROIDS,
        **TWIN_CITIES_CITY_CENTROIDS,
    }

    def geocode(self, location: str) -> tuple[float, float] | None:
        return self.locations.get(location.lower().strip())
