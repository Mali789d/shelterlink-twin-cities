import re
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
    "north st paul": (45.014551, -93.025535),
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
    "west st paul": (44.912692, -93.090059),
    "white bear lake": (45.078907, -92.979715),
    "woodbury": (44.918031, -92.938277),
}

# Well-known Minneapolis neighborhoods and Saint Paul planning districts people
# actually text ("Frogtown", "Uptown", "the Midway") far more often than a ZIP.
# Each resolves to the centroid of its primary ZIP above, never an exact address.
# Minneapolis names follow the zipdatamaps.com Minneapolis neighborhood-to-ZIP
# listing; Saint Paul names follow the mytwincitiesrealty.com district-to-ZIP
# listing (both checked October 2026). Ambiguous names stay unknown on purpose:
# "Como" is a Minneapolis neighborhood (55414) AND Saint Paul's Como Park
# (55108), bare "Downtown" is both cities, and "St Anthony" is both a suburb
# and a Saint Paul park district - a guess would send someone across town.
TWIN_CITIES_NEIGHBORHOOD_CENTROIDS: dict[str, tuple[float, float]] = {
    # Minneapolis
    "uptown": TWIN_CITIES_ZIP_CENTROIDS["55408"],
    "dinkytown": TWIN_CITIES_ZIP_CENTROIDS["55414"],
    "north loop": TWIN_CITIES_ZIP_CENTROIDS["55401"],
    "cedar riverside": TWIN_CITIES_ZIP_CENTROIDS["55454"],
    "west bank": TWIN_CITIES_ZIP_CENTROIDS["55454"],
    "northeast": TWIN_CITIES_ZIP_CENTROIDS["55413"],
    "northeast minneapolis": TWIN_CITIES_ZIP_CENTROIDS["55413"],
    "nordeast": TWIN_CITIES_ZIP_CENTROIDS["55413"],
    "longfellow": TWIN_CITIES_ZIP_CENTROIDS["55406"],
    "powderhorn": TWIN_CITIES_ZIP_CENTROIDS["55407"],
    "powderhorn park": TWIN_CITIES_ZIP_CENTROIDS["55407"],
    "whittier": TWIN_CITIES_ZIP_CENTROIDS["55404"],
    "seward": TWIN_CITIES_ZIP_CENTROIDS["55406"],
    "linden hills": TWIN_CITIES_ZIP_CENTROIDS["55410"],
    "nokomis": TWIN_CITIES_ZIP_CENTROIDS["55417"],
    "camden": TWIN_CITIES_ZIP_CENTROIDS["55412"],
    "near north": TWIN_CITIES_ZIP_CENTROIDS["55411"],
    "loring park": TWIN_CITIES_ZIP_CENTROIDS["55403"],
    "elliot park": TWIN_CITIES_ZIP_CENTROIDS["55404"],
    "hawthorne": TWIN_CITIES_ZIP_CENTROIDS["55411"],
    "downtown minneapolis": TWIN_CITIES_CITY_CENTROIDS["minneapolis"],
    "marcy holmes": TWIN_CITIES_ZIP_CENTROIDS["55414"],
    "prospect park": TWIN_CITIES_ZIP_CENTROIDS["55414"],
    "king field": TWIN_CITIES_ZIP_CENTROIDS["55409"],
    "kingfield": TWIN_CITIES_ZIP_CENTROIDS["55409"],
    "tangletown": TWIN_CITIES_ZIP_CENTROIDS["55419"],
    "bryn mawr": TWIN_CITIES_ZIP_CENTROIDS["55405"],
    "minnehaha": TWIN_CITIES_ZIP_CENTROIDS["55417"],
    # Saint Paul
    "frogtown": TWIN_CITIES_ZIP_CENTROIDS["55103"],
    "thomas dale": TWIN_CITIES_ZIP_CENTROIDS["55103"],
    "midway": TWIN_CITIES_ZIP_CENTROIDS["55104"],
    "como park": TWIN_CITIES_ZIP_CENTROIDS["55108"],
    "daytons bluff": TWIN_CITIES_ZIP_CENTROIDS["55106"],
    "payne phalen": TWIN_CITIES_ZIP_CENTROIDS["55130"],
    "north end": TWIN_CITIES_ZIP_CENTROIDS["55117"],
    "west side": TWIN_CITIES_ZIP_CENTROIDS["55107"],
    "west seventh": TWIN_CITIES_ZIP_CENTROIDS["55102"],
    "west 7th": TWIN_CITIES_ZIP_CENTROIDS["55102"],
    "summit university": TWIN_CITIES_ZIP_CENTROIDS["55104"],
    "macalester groveland": TWIN_CITIES_ZIP_CENTROIDS["55105"],
    "mac groveland": TWIN_CITIES_ZIP_CENTROIDS["55105"],
    "highland park": TWIN_CITIES_ZIP_CENTROIDS["55116"],
    "summit hill": TWIN_CITIES_ZIP_CENTROIDS["55105"],
    "downtown saint paul": TWIN_CITIES_CITY_CENTROIDS["saint paul"],
    "downtown st paul": TWIN_CITIES_CITY_CENTROIDS["saint paul"],
    "lowertown": TWIN_CITIES_ZIP_CENTROIDS["55101"],
    "st anthony park": TWIN_CITIES_ZIP_CENTROIDS["55108"],
    "union park": TWIN_CITIES_ZIP_CENTROIDS["55104"],
    "merriam park": TWIN_CITIES_ZIP_CENTROIDS["55104"],
    "battle creek": TWIN_CITIES_ZIP_CENTROIDS["55119"],
}


class DevelopmentGeocoder:
    """Deterministic local map for development; replace before launch.

    Every covered metro ZIP (Hennepin and Ramsey counties plus metro-adjacent
    ZIPs), the municipalities those ZIPs belong to, and well-known Minneapolis
    neighborhoods and Saint Paul districts resolve to an approximate centroid -
    never an exact address.
    """

    locations = {
        **TWIN_CITIES_ZIP_CENTROIDS,
        **TWIN_CITIES_CITY_CENTROIDS,
        **TWIN_CITIES_NEIGHBORHOOD_CENTROIDS,
    }

    def geocode(self, location: str) -> tuple[float, float] | None:
        # Same 100-character bound as web/zip-lookup.mjs lookupPlace: place
        # text longer than that is rejected, not trimmed into a match.
        if len(location) > 100:
            return None
        text = normalize_place(location)
        found = self.locations.get(text)
        if found is not None:
            return found
        # Natural phrasing keeps its preposition ("meal near Frogtown"): try the
        # place without one leading preposition, but only after the literal text
        # failed - "Near North" is a real Minneapolis neighborhood and must not
        # be mangled to "north". Mirrors web/zip-lookup.mjs lookupPlace.
        first, separator, rest = text.partition(" ")
        if separator and first in LEADING_PREPOSITIONS:
            return self.locations.get(rest)
        return None


# Natural phrasing puts one of these before the place ("shelter in Minneapolis",
# "food near Frogtown"); the geocoder forgives a single leading one. Imported by
# app/sms.py for its lone-preposition guard and mirrored by
# web/zip-lookup.mjs - keep all three in sync.
LEADING_PREPOSITIONS = ("in", "near", "around", "at", "by")


# Texting variants of the same place: a trailing state name, abbreviation
# periods (St.), apostrophes, hyphens and stray whitespace never change which
# city the sender means.
_STATE_SUFFIX = re.compile(r"\s*,?\s*(?:mn|minnesota)$")
_LETTER_PERIOD = re.compile(r"(?<=[a-z])\.")


def normalize_place(text: str) -> str:
    """Canonical lookup key for a texted place; unknown input stays unknown."""
    # Apostrophes (straight or curled by autocorrect) and hyphens are texting
    # formatting, not different places: "Dayton's Bluff", "daytons bluff" and
    # "Payne-Phalen" all mean the same district.
    text = text.lower().replace("'", "").replace("\u2019", "").replace("-", " ")
    text = " ".join(text.split())
    text = _LETTER_PERIOD.sub("", text)
    return _STATE_SUFFIX.sub("", text).strip(" ,")


# Explicit "latitude, longitude" text: decimal degrees, comma separated, in
# range. ASCII digits only, matching web/location-input.mjs parseCoordinates:
# \d would also match Unicode decimal digits (float() parses those), so the SMS
# geocoder would accept coordinates the web page rejects.
_COORDINATES_PATTERN = re.compile(
    r"^\s*([+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+))\s*,"
    r"\s*([+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+))\s*$"
)


def parse_coordinates(text: str) -> tuple[float, float] | None:
    """Explicit "latitude, longitude" text, or None for anything else.

    Mirrors web/location-input.mjs parseCoordinates: only decimal degrees within
    range - never a guessed ZIP, address or direction. Both groups come from a
    digits-only pattern, so the floats are always finite.
    """
    if len(text) > 100:
        return None
    match = _COORDINATES_PATTERN.match(text)
    if not match:
        return None
    latitude, longitude = float(match[1]), float(match[2])
    if abs(latitude) > 90 or abs(longitude) > 180:
        return None
    return latitude, longitude
