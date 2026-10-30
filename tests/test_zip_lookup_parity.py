"""The static page's offline place map must stay identical to the Python geocoder."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.geocoding import (
    DevelopmentGeocoder,
    TWIN_CITIES_CITY_CENTROIDS,
    TWIN_CITIES_NEIGHBORHOOD_CENTROIDS,
)
from app.zip_centroids import TWIN_CITIES_ZIP_CENTROIDS

REPO = Path(__file__).parent.parent


def javascript_maps():
    if not shutil.which("node"):
        pytest.skip("Node is required for JS/Python parity tests")
    script = (
        "import('./web/zip-lookup.mjs').then(m => console.log(JSON.stringify({"
        "zips: m.ZIP_CENTROIDS, cities: m.CITY_CENTROIDS,"
        "neighborhoods: m.NEIGHBORHOOD_CENTROIDS,"
        "lookups: [m.lookupPlace('55415'), m.lookupPlace(' Minneapolis '),"
        " m.lookupPlace('10001'), m.lookupPlace(42),"
        " m.lookupPlace('St. Paul, MN'), m.lookupPlace('mn'),"
        " m.lookupPlace('Frogtown'), m.lookupPlace('North-Loop'),"
        " m.lookupPlace('Dayton\\u2019s Bluff'), m.lookupPlace('como'),"
        " m.lookupPlace('constructor'), m.lookupPlace('__proto__')]})))"
    )
    result = subprocess.run(["node", "-e", script], cwd=REPO,
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_zip_centroids_match_exactly():
    js_zips = javascript_maps()["zips"]
    assert len(js_zips) == len(TWIN_CITIES_ZIP_CENTROIDS) == 103
    for zip_code, (latitude, longitude) in TWIN_CITIES_ZIP_CENTROIDS.items():
        place = js_zips[zip_code]
        assert place["latitude"] == pytest.approx(latitude, abs=1e-9), zip_code
        assert place["longitude"] == pytest.approx(longitude, abs=1e-9), zip_code


def test_city_entries_match_the_python_geocoder():
    js_cities = javascript_maps()["cities"]
    assert len(TWIN_CITIES_CITY_CENTROIDS) == 49
    assert set(js_cities) == set(TWIN_CITIES_CITY_CENTROIDS)
    for name, (latitude, longitude) in TWIN_CITIES_CITY_CENTROIDS.items():
        assert js_cities[name]["latitude"] == pytest.approx(latitude, abs=1e-9), name
        assert js_cities[name]["longitude"] == pytest.approx(longitude, abs=1e-9), name


def test_neighborhood_entries_match_the_python_geocoder():
    js_neighborhoods = javascript_maps()["neighborhoods"]
    assert len(TWIN_CITIES_NEIGHBORHOOD_CENTROIDS) == 50
    assert set(js_neighborhoods) == set(TWIN_CITIES_NEIGHBORHOOD_CENTROIDS)
    for name, (latitude, longitude) in TWIN_CITIES_NEIGHBORHOOD_CENTROIDS.items():
        assert js_neighborhoods[name]["latitude"] == pytest.approx(latitude, abs=1e-9), name
        assert js_neighborhoods[name]["longitude"] == pytest.approx(longitude, abs=1e-9), name


def test_lookup_behavior_matches_python_semantics():
    lookups = javascript_maps()["lookups"]
    python = DevelopmentGeocoder()
    assert lookups[0]["latitude"] == pytest.approx(python.geocode("55415")[0], abs=1e-9)
    assert lookups[1]["latitude"] == pytest.approx(python.geocode(" Minneapolis ")[0], abs=1e-9)
    assert lookups[2] is None and lookups[3] is None
    assert lookups[4]["latitude"] == pytest.approx(
        python.geocode("St. Paul, MN")[0], abs=1e-9)
    assert lookups[5] is None
    # Neighborhoods resolve identically on both sides, including the texting
    # variants (hyphens, autocorrect-curled apostrophes) each normalizer folds.
    assert lookups[6]["latitude"] == pytest.approx(python.geocode("Frogtown")[0], abs=1e-9)
    assert lookups[6]["longitude"] == pytest.approx(python.geocode("Frogtown")[1], abs=1e-9)
    assert lookups[7]["latitude"] == pytest.approx(python.geocode("North-Loop")[0], abs=1e-9)
    assert lookups[7]["longitude"] == pytest.approx(python.geocode("North-Loop")[1], abs=1e-9)
    assert lookups[8]["latitude"] == pytest.approx(
        python.geocode("Dayton\u2019s Bluff")[0], abs=1e-9)
    # "Como" names a Minneapolis neighborhood AND a Saint Paul district:
    # both sides stay silent rather than guess a city.
    assert lookups[9] is None and python.geocode("como") is None
    # Inherited Object member names resolve to nothing, like Python's dict.
    assert lookups[10] is None and lookups[11] is None
    assert python.geocode("constructor") is None and python.geocode("__proto__") is None
