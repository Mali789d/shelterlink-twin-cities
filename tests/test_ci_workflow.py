"""The CI workflow must run every JavaScript test file, not a lucky prefix.

The node step once globbed tests/test_web_*.mjs, which silently excluded
tests/test_verified_directory.mjs - the file that runs the real verified
provider seed through the browser reader. Nothing failed: CI stayed green
while 4 tests never ran. Expand the workflow's own node --test globs and
compare them to the tests on disk so a renamed or newly added file that
falls outside the pattern fails this suite instead of rotting in place.
"""
import glob
import re
from pathlib import Path

REPO = Path(__file__).parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


def test_node_job_runs_every_js_test_file():
    text = WORKFLOW.read_text(encoding="utf-8")
    patterns = re.findall(r"node --test\s+(\S+)", text)
    assert patterns, "ci.yml has no node --test step"
    covered = set()
    for pattern in patterns:
        matched = glob.glob(str(REPO / pattern))
        assert matched, f"CI node glob matches nothing: {pattern}"
        covered.update(matched)
    expected = set(glob.glob(str(REPO / "tests" / "*.mjs")))
    assert expected, "no JavaScript tests found on disk"
    missing = sorted(expected - covered)
    assert not missing, f"CI never runs these JS tests: {missing}"
