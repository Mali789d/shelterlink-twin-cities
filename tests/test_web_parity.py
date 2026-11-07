"""Cross-side invariants between the Python exporter and the static page.

Two values must never drift apart, and until now only comments said so:

- The 211/911 safety notice is one wording across the exporter and every page
  module. A rewording on either side would silently split the safety guidance
  shown to people in crisis.
- The freshness window (app/freshness.py DEFAULT_MAX_AGE, web/directory.mjs
  MAX_AGE_MS) decides what counts as current. Drift would make the page show
  listings the API considers stale, or hide listings the API still serves.

Same pattern as tests/test_zip_lookup_parity.py: read the JavaScript values
straight out of the real modules and compare them to the Python constants.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.export_directory import DIRECTORY_NOTICE
from app.freshness import DEFAULT_MAX_AGE

REPO = Path(__file__).parent.parent


def javascript_values():
    if not shutil.which("node"):
        pytest.skip("Node is required for JS/Python parity tests")
    script = (
        "Promise.all([import('./web/directory.mjs'),"
        " import('./web/directory-session.mjs'),"
        " import('./web/directory-view.mjs')]).then(([reader, session, view]) =>"
        " console.log(JSON.stringify({"
        "readerNotice: reader.DIRECTORY_NOTICE,"
        "sessionNotice: session.NOTICE,"
        "viewNotice: view.PAGE_NOTICE,"
        "maxAgeMs: reader.MAX_AGE_MS})))"
    )
    result = subprocess.run(["node", "-e", script], cwd=REPO,
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_safety_notice_is_one_wording_across_both_sides():
    values = javascript_values()
    copies = {
        "python exporter": DIRECTORY_NOTICE,
        "web directory reader": values["readerNotice"],
        "web directory session": values["sessionNotice"],
        "web directory view": values["viewNotice"],
    }
    assert "211" in DIRECTORY_NOTICE and "911" in DIRECTORY_NOTICE
    assert len(set(copies.values())) == 1, copies


def test_freshness_window_matches_on_both_sides():
    values = javascript_values()
    assert values["maxAgeMs"] == int(DEFAULT_MAX_AGE.total_seconds() * 1000)
