"""The development geocoder covers Twin Cities metro ZIPs with sane centroids."""
import re

from app.geocoding import DevelopmentGeocoder, parse_coordinates
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
    city_entries = {name: coords for name, coords in geocoder.locations.items()
                    if not name.isdigit()}
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
