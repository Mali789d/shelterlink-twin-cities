"""The development geocoder covers Twin Cities metro ZIPs with sane centroids."""
import re

from app.geocoding import (
    DevelopmentGeocoder,
    TWIN_CITIES_CITY_CENTROIDS,
    TWIN_CITIES_NEIGHBORHOOD_CENTROIDS,
    parse_coordinates,
)
from app.search import validate_coordinates
from app.zip_centroids import TWIN_CITIES_ZIP_CENTROIDS

# Loose box around the Twin Cities metro; a centroid outside it is a data error.
TWIN_CITIES_BOX = (44.70, 45.25, -93.75, -92.85)


def test_every_core_city_zip_resolves_to_a_valid_centroid():
    geocoder = DevelopmentGeocoder()
    assert len(TWIN_CITIES_ZIP_CENTROIDS) == 103
    for zip_code, (latitude, longitude) in TWIN_CITIES_ZIP_CENTROIDS.items():
        assert re.fullmatch(r"55[134]\d{2}", zip_code)
        validate_coordinates(latitude, longitude)
        lat_min, lat_max, lng_min, lng_max = TWIN_CITIES_BOX
        assert lat_min <= latitude <= lat_max, zip_code
        assert lng_min <= longitude <= lng_max, zip_code
        assert geocoder.geocode(zip_code) == (latitude, longitude)


def test_downtown_minneapolis_zip_lands_downtown():
    latitude, longitude = DevelopmentGeocoder().geocode("55401")
    # A centroid may drift within the ZIP but must stay near the core.
    assert abs(latitude - 44.98) < 0.02 and abs(longitude - -93.27) < 0.02


def test_lookup_trims_case_and_whitespace_for_names():
    geocoder = DevelopmentGeocoder()
    assert geocoder.geocode("  Minneapolis ") == geocoder.geocode("minneapolis")
    assert geocoder.geocode("Saint Paul") == geocoder.geocode("st paul")


def test_lookup_forgives_common_texting_variants():
    geocoder = DevelopmentGeocoder()
    saint_paul = geocoder.locations["saint paul"]
    assert geocoder.geocode("St. Paul") == saint_paul
    assert geocoder.geocode("ST. PAUL, MN") == saint_paul
    assert geocoder.geocode("Saint Paul, Minnesota") == saint_paul
    assert geocoder.geocode("st.  louis   park") == geocoder.locations["st louis park"]
    assert geocoder.geocode("west st. paul") == geocoder.locations["west saint paul"]
    assert geocoder.geocode("north st paul") == geocoder.locations["north saint paul"]
    assert geocoder.geocode("Maple Grove MN") == geocoder.locations["maple grove"]
    assert geocoder.geocode("55401 mn") == geocoder.locations["55401"]


def test_lookup_variants_never_guess_a_place():
    geocoder = DevelopmentGeocoder()
    assert geocoder.geocode("mn") is None
    assert geocoder.geocode("minnesota") is None
    assert geocoder.geocode("duluth mn") is None  # a real place, outside our map
    assert geocoder.geocode("st.paul") is None  # no space is a different token
    assert geocoder.geocode("5540.1") is None  # a stray period never makes a ZIP


def test_unknown_locations_return_none():
    geocoder = DevelopmentGeocoder()
    assert geocoder.geocode("10001") is None  # outside the Twin Cities
    assert geocoder.geocode("nowhere particular") is None
    assert geocoder.geocode("") is None


def test_original_zip_entries_still_resolve():
    geocoder = DevelopmentGeocoder()
    for zip_code in ("55415", "55404", "55101"):
        assert geocoder.geocode(zip_code) is not None


def test_zip_keys_are_five_digits_and_unique():
    keys = list(TWIN_CITIES_ZIP_CENTROIDS)
    assert len(keys) == len(set(keys))
    assert all(re.fullmatch(r"\d{5}", key) for key in keys)


def test_city_centroids_stay_on_their_own_sides_of_the_river():
    geocoder = DevelopmentGeocoder()
    _, minneapolis_lng = geocoder.geocode("minneapolis")
    _, saint_paul_lng = geocoder.geocode("saint paul")
    # Minneapolis sits west of Saint Paul; a swapped entry would flip this.
    assert minneapolis_lng < saint_paul_lng


def test_metro_city_names_resolve_to_metro_centroids():
    geocoder = DevelopmentGeocoder()
    city_entries = TWIN_CITIES_CITY_CENTROIDS
    assert len(city_entries) == 49
    lat_min, lat_max, lng_min, lng_max = TWIN_CITIES_BOX
    for name, (latitude, longitude) in city_entries.items():
        assert re.fullmatch(r"[a-z ]+", name)
        assert lat_min < latitude < lat_max, name
        assert lng_min < longitude < lng_max, name
    assert geocoder.geocode("Maple Grove") == geocoder.locations["maple grove"]
    assert geocoder.geocode("Eden Prairie") == geocoder.locations["eden prairie"]
    assert geocoder.geocode("nowhereville") is None


def test_parse_coordinates_accepts_only_explicit_in_range_pairs():
    assert parse_coordinates("44.9778,-93.2650") == (44.9778, -93.2650)
    assert parse_coordinates("44.9778, -93.2650") == (44.9778, -93.2650)
    assert parse_coordinates(" 44.9 , -93.1 ") == (44.9, -93.1)
    assert parse_coordinates(".5,-93") == (0.5, -93.0)
    assert parse_coordinates("0,0") == (0.0, 0.0)
    for rejected in ("55401", "maple grove", "44.9 -93.1", "91,0", "0,-181",
                     "12,34,56", "", "Infinity,0", "44.9,",
                     "44." + "0" * 100 + ",-93"):
        assert parse_coordinates(rejected) is None, rejected
def test_neighborhoods_resolve_to_their_primary_zip_centroid():
    geocoder = DevelopmentGeocoder()
    assert len(TWIN_CITIES_NEIGHBORHOOD_CENTROIDS) == 50
    downtowns = {geocoder.locations["minneapolis"], geocoder.locations["saint paul"]}
    lat_min, lat_max, lng_min, lng_max = TWIN_CITIES_BOX
    for name, centroid in TWIN_CITIES_NEIGHBORHOOD_CENTROIDS.items():
        # Every neighborhood borrows an existing ZIP (or downtown) centroid:
        # the only new data here is the name-to-place mapping, never coordinates.
        assert centroid in set(TWIN_CITIES_ZIP_CENTROIDS.values()) | downtowns, name
        validate_coordinates(*centroid)
        assert lat_min <= centroid[0] <= lat_max and lng_min <= centroid[1] <= lng_max, name
        assert geocoder.geocode(name) == centroid


def test_neighborhood_lookup_spot_checks():
    geocoder = DevelopmentGeocoder()
    assert geocoder.geocode("frogtown") == TWIN_CITIES_ZIP_CENTROIDS["55103"]
    assert geocoder.geocode("uptown") == TWIN_CITIES_ZIP_CENTROIDS["55408"]
    assert geocoder.geocode("cedar riverside") == TWIN_CITIES_ZIP_CENTROIDS["55454"]
    assert geocoder.geocode("downtown minneapolis") == geocoder.locations["minneapolis"]
    assert geocoder.geocode("downtown st paul") == geocoder.locations["saint paul"]


def test_neighborhood_lookup_forgives_texting_variants():
    geocoder = DevelopmentGeocoder()
    assert geocode_pair(geocoder, "North-Loop", "north loop")
    assert geocode_pair(geocoder, "Dayton's Bluff", "daytons bluff")
    assert geocode_pair(geocoder, "Dayton\u2019s Bluff", "daytons bluff")
    assert geocode_pair(geocoder, "payne-phalen", "payne phalen")
    assert geocode_pair(geocoder, "MAC-GROVELAND", "mac groveland")
    assert geocoder.geocode("west 7th") == geocoder.geocode("west seventh")
    assert geocoder.geocode("Frogtown, MN") == geocoder.geocode("frogtown")


def geocode_pair(geocoder, variant, canonical):
    result = geocoder.geocode(variant)
    assert result is not None
    return result == geocoder.geocode(canonical)


def test_ambiguous_neighborhood_names_stay_unknown():
    geocoder = DevelopmentGeocoder()
    # "Como" is a Minneapolis neighborhood (55414) AND Saint Paul's Como Park
    # (55108); bare "Downtown" is both cities; "St Anthony" is a suburb and a
    # park district; "Jordan" is a Minneapolis neighborhood and a Scott County
    # city; "Windom" is a Minneapolis neighborhood and a southwest MN city.
    # A wrong guess here sends a person across town, so none of these resolve.
    for ambiguous in ("como", "downtown", "st anthony", "jordan", "windom",
                      "riverside", "uptown minneapolis"):
        assert geocoder.geocode(ambiguous) is None, ambiguous


def test_leading_preposition_falls_back_only_after_literal_miss():
    geocoder = DevelopmentGeocoder()
    # Natural phrasing keeps its preposition and still lands on the place.
    assert geocoder.geocode("in minneapolis") == geocoder.geocode("minneapolis")
    assert geocoder.geocode("near frogtown") == geocoder.geocode("frogtown")
    assert geocoder.geocode("around saint paul") == geocoder.geocode("saint paul")
    assert geocoder.geocode("at minneapolis") == geocoder.geocode("minneapolis")
    assert geocoder.geocode("by uptown") == geocoder.geocode("uptown")
    # 'Near North' is a real neighborhood: the literal lookup must win over
    # stripping 'near', which would leave the neighborhood unreachable.
    assert geocoder.geocode("north") is None
    assert geocoder.geocode("near north") is not None


def test_lone_preposition_stays_unknown():
    geocoder = DevelopmentGeocoder()
    for lone in ("in", "near", "around", "at", "by"):
        assert geocoder.geocode(lone) is None, lone
    # Forgiving a preposition never un-ambiguates a genuinely ambiguous place.
    assert geocoder.geocode("near como") is None
    assert geocoder.geocode("in downtown") is None
