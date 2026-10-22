"""The development geocoder covers Twin Cities metro ZIPs with sane centroids."""
import re

from app.geocoding import DevelopmentGeocoder
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
