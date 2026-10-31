"""The SMS geocoder and the static page must interpret the same texted location
identically: the same strings parse on both channels and the same strings are
rejected. Divergent parsing means a sender gets a location on one channel and
a "try again" on the other, so parity is locked here over tricky inputs."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.geocoding import DevelopmentGeocoder, parse_coordinates

REPO = Path(__file__).parent.parent

COORDINATE_INPUTS = [
    "44.98, -93.27",
    " 44.98 , -93.27 ",
    "+44.9,-93.2",
    ".5, .6",
    "044.98, -093.27",
    "-90, -180",
    "90, 180",
    "44.98",
    "44.98,",
    "44..9, -93",
    "4a, 5",
    "1e2, 3",
    "91, 0",
    "0, 181",
    "44.9 ,",
    " , -93.2",
    "",
    "   ",
    "\u0664\u0664.\u0669, -\u0669\u0663.\u0662\u0667",  # Arabic-Indic digits
    "\uff14\uff14.\uff19, -\uff19\uff13.\uff12\uff17",  # full-width digits
    "44.9, -93.2 " + " " * 100,
]

PLACE_INPUTS = [
    "55401",
    " 55401 ",
    "55401 mn",
    "55401,",
    "55415",
    "St. Paul, MN",
    "ST PAUL MINNESOTA",
    "saint paul minnesota",
    "minneapolis",
    "Minneapolis,",
    "st.  louis   park",
    "west st. paul",
    "Maple Grove MN",
    "woodBURY",
    "st.paul",
    "10001",
    "mn",
    "minnesota",
    ",,,",
    "minneapolis" + " " * 95,
    "in minneapolis",
    "near frogtown",
    "near north",
    "near",
    "at",
    "by uptown",
]


def javascript_results():
    if not shutil.which("node"):
        pytest.skip("Node is required for JS/Python parity tests")
    inputs = json.dumps({"coordinates": COORDINATE_INPUTS, "places": PLACE_INPUTS})
    script = (
        f"const inputs = {inputs};"
        "Promise.all([import('./web/location-input.mjs'), import('./web/zip-lookup.mjs')])"
        ".then(([location, places]) => {"
        "const coordinates = inputs.coordinates.map(text => {"
        "try { const parsed = location.parseCoordinates(text);"
        " return {ok: true, latitude: parsed.latitude, longitude: parsed.longitude};"
        "} catch { return {ok: false}; }});"
        "const lookups = inputs.places.map(text => places.lookupPlace(text) ?? null);"
        "console.log(JSON.stringify({coordinates, lookups}));})"
    )
    result = subprocess.run(["node", "-e", script], cwd=REPO,
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_coordinate_parsing_matches_on_both_channels():
    results = javascript_results()["coordinates"]
    assert len(results) == len(COORDINATE_INPUTS)
    for text, js in zip(COORDINATE_INPUTS, results):
        python = parse_coordinates(text)
        if not js["ok"]:
            assert python is None, f"Python accepted {text!r} the page rejects"
        else:
            assert python is not None, f"Python rejected {text!r} the page parses"
            assert python[0] == pytest.approx(js["latitude"], abs=1e-9), text
            assert python[1] == pytest.approx(js["longitude"], abs=1e-9), text


def test_place_lookup_matches_on_both_channels():
    results = javascript_results()["lookups"]
    assert len(results) == len(PLACE_INPUTS)
    python = DevelopmentGeocoder()
    for text, js in zip(PLACE_INPUTS, results):
        parsed = python.geocode(text)
        if js is None:
            assert parsed is None, f"Python accepted {text!r} the page rejects"
        else:
            assert parsed is not None, f"Python rejected {text!r} the page resolves"
            assert parsed[0] == pytest.approx(js["latitude"], abs=1e-9), text
            assert parsed[1] == pytest.approx(js["longitude"], abs=1e-9), text
