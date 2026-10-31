"""Tie handling must be deterministic and identical across SMS, API and web.

Co-located services - a shelter and a meal program sharing one address - tie on
every nearby search. Python ranks those ties by resource id, exactly like
web/directory.mjs nearbyResources, so a data-file reorder never changes which
resources a reply lists, or which ones make the cut at the limit. (Ids are
operator-controlled ASCII slugs, for which JavaScript and Python string order
agree.)
"""
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.data import DATA_PATH, load_resources
from app.search import find_resources

AT = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
REPO = Path(__file__).parent.parent


def colocated(identity):
    return load_resources()[0].model_copy(update={
        "id": identity, "name": f"Site {identity}",
        "latitude": 45.0, "longitude": -93.0,
        "verified_at": AT, "is_sample": False,
    })


def test_limit_cut_under_ties_selects_the_id_first_set():
    records = [colocated("c-site"), colocated("b-site"), colocated("a-site")]
    results = find_resources(records, 45.0, -93.0, limit=2, at=AT)
    assert [item.resource.id for item in results] == ["a-site", "b-site"]
    reversed_records = list(reversed(records))
    results = find_resources(reversed_records, 45.0, -93.0, limit=2, at=AT)
    assert [item.resource.id for item in results] == ["a-site", "b-site"]


def test_distance_still_outranks_id_order():
    farther_a = colocated("a-site").model_copy(update={"latitude": 45.05})
    results = find_resources([farther_a, colocated("b-site")], 45.0, -93.0, at=AT)
    assert [item.resource.id for item in results] == ["b-site", "a-site"]


def test_api_results_follow_the_same_deterministic_order(monkeypatch):
    monkeypatch.setattr(main, "resources",
                        [colocated("b-site"), colocated("a-site")])
    response = TestClient(main.app).get("/resources/search",
                                        params={"location": "45.0,-93.0"})
    assert response.status_code == 200
    assert [item["resource"]["id"] for item in response.json()] == ["a-site", "b-site"]


def test_web_nearby_ranks_the_same_fixture_identically():
    if not shutil.which("node"):
        pytest.skip("Node is required for JS/Python parity tests")
    record = json.loads(DATA_PATH.read_text())[0]
    timestamp = AT.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    def entry(identity):
        return {**record, "id": identity, "name": f"Site {identity}",
                "latitude": 45.0, "longitude": -93.0,
                "verified_at": timestamp, "is_sample": False}

    snapshot = {"schema_version": 1, "generated_at": timestamp,
                "resources": [entry("b-site"), entry("a-site")]}
    script = (
        "import('./web/directory.mjs').then(m => {"
        f"const now = {int(AT.timestamp() * 1000)};"
        f"const directory = m.readDirectory({json.dumps(snapshot)}, now);"
        "const found = m.nearbyResources(directory,"
        "{latitude: 45, longitude: -93, limit: 10, now});"
        "console.log(JSON.stringify(found.map(r => r.resource.id)));})"
    )
    result = subprocess.run(["node", "-e", script], cwd=REPO,
                            capture_output=True, text=True, check=True)
    js_order = json.loads(result.stdout)
    python_order = [item.resource.id for item in find_resources(
        [colocated("b-site"), colocated("a-site")], 45.0, -93.0, limit=10, at=AT)]
    assert js_order == ["a-site", "b-site"] == python_order
