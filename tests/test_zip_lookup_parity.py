"""The static page's offline place map must stay identical to the Python geocoder."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.geocoding import DevelopmentGeocoder
from app.zip_centroids import TWIN_CITIES_ZIP_CENTROIDS

REPO = Path(__file__).parent.parent


def javascript_maps():
    if not shutil.which("node"):
        pytest.skip("Node is required for JS/Python parity tests")
    script = (
        "import('./web/zip-lookup.mjs').then(m => console.log(JSON.stringify({"
        "zips: m.ZIP_CENTROIDS, cities: m.CITY_CENTROIDS,"
        "lookups: [m.lookupPlace('55415'), m.lookupPlace(' Minneapolis '),"
        " m.lookupPlace('10001'), m.lookupPlace(42)]})))"
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
    python = DevelopmentGeocoder().locations
    expected = {name: coords for name, coords in python.items()
                if not name.isdigit()}
    assert len(expected) == 47
    assert set(js_cities) == set(expected)
    for name, (latitude, longitude) in expected.items():
        assert js_cities[name]["latitude"] == pytest.approx(latitude, abs=1e-9), name
        assert js_cities[name]["longitude"] == pytest.approx(longitude, abs=1e-9), name


def test_lookup_behavior_matches_python_semantics():
    lookups = javascript_maps()["lookups"]
    python = DevelopmentGeocoder()
    assert lookups[0]["latitude"] == pytest.approx(python.geocode("55415")[0], abs=1e-9)
    assert lookups[1]["latitude"] == pytest.approx(python.geocode(" Minneapolis ")[0], abs=1e-9)
    assert lookups[2] is None and lookups[3] is None
