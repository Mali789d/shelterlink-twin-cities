"""Exercise exported Python data through the actual browser session/loader stack.

All listings are synthetic fixtures. These tests prove interoperability, not provenance.
"""
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.data import load_resources
from app.export_directory import directory_snapshot

NOW = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)


def exported():
    item = load_resources()[0].model_copy(update={
        "id": "contract-fixture", "name": "Synthetic contract fixture",
        "is_sample": False, "verified_at": NOW, "latitude": 0, "longitude": 0,
    })
    return directory_snapshot([item], NOW)


@pytest.mark.parametrize("scenario", [
    "results", "no_matches", "expiry", "bad_source", "bad_coordinate",
    "bad_timestamp", "duplicate", "invalid_version", "failed_refresh",
])
def test_python_export_through_browser_refresh_session(tmp_path, scenario):
    if not shutil.which("node"):
        pytest.skip("Node is required for browser contract tests")
    data = exported()
    if scenario == "bad_source":
        data["resources"][0]["source_url"] = "javascript:alert(1)"
    elif scenario == "bad_coordinate":
        data["resources"][0]["latitude"] = 91
    elif scenario == "bad_timestamp":
        data["resources"][0]["verified_at"] = "2026-02-30T12:00:00Z"
    elif scenario == "duplicate":
        data["resources"].append(data["resources"][0])
    elif scenario == "invalid_version":
        data["schema_version"] = 2
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    session_module = Path("web/directory-session.mjs").resolve().as_uri()
    loader_module = Path("web/directory-loader.mjs").resolve().as_uri()
    now_ms = int(NOW.timestamp() * 1000)
    category = data["resources"][0]["category"]
    other = "shower" if category != "shower" else "meal"
    expected = "unavailable" if scenario.startswith("bad_") or scenario in {
        "duplicate", "invalid_version"
    } else "no_matches" if scenario == "no_matches" else "results"
    script = f'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {{createDirectorySession}} from {json.dumps(session_module)};
import {{createDirectoryLoader}} from {json.dumps(loader_module)};
let now = {now_ms};
const session = createDirectorySession(() => now);
const snapshot = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
let fail = false;
const loader = createDirectoryLoader(session, async () => {{
  if (fail) throw new Error('synthetic offline failure');
  return snapshot;
}});
session.search({{latitude: 0, longitude: 0, category: {json.dumps(other if scenario == 'no_matches' else category)}}});
const state = await loader.refresh();
assert.equal(state.status, {json.dumps(expected)});
assert.match(state.notice, /211.*911/);
if (state.status === 'results') {{
  assert.equal(state.results[0].resource.id, 'contract-fixture');
  assert.equal(state.results[0].distanceMiles, 0);
  for (const field of ['availability', 'hours', 'open_now', 'is_sample']) {{
    assert.equal(field in state.results[0].resource, false);
  }}
}}
if ({json.dumps(scenario)} === 'expiry') {{
  now += 86400001;
  assert.equal(session.getState().status, 'refresh_required');
  assert.equal(session.getState().results.length, 0);
}}
if ({json.dumps(scenario)} === 'failed_refresh') {{
  fail = true;
  const failed = await loader.refresh();
  assert.equal(failed.status, 'unavailable');
  assert.equal(failed.results.length, 0);
  assert.match(failed.notice, /211.*911/);
}}
'''
    result = subprocess.run(["node", "--input-type=module", "-e", script, str(path)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
