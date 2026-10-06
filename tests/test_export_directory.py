import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from app.data import load_resources
from app.export_directory import directory_snapshot
from app.models import Availability

NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def reviewed():
    return load_resources()[0].model_copy(update={
        "is_sample": False, "verified_at": NOW, "availability": Availability.AVAILABLE,
    })


def test_export_is_directory_only_with_provenance_and_safety_notice():
    result = directory_snapshot([reviewed()], NOW)
    text = json.dumps(result)
    for forbidden in ("availability", "open_now", "hours", "is_sample"):
        assert forbidden not in result["resources"][0]
    assert "211" in result["notice"] and "911" in result["notice"]
    assert result["resources"][0]["source_url"]
    assert result["resources"][0]["verified_at"]
    assert "available" not in text


@pytest.mark.parametrize("kind", ["empty", "sample", "stale", "future", "naive"])
def test_export_rejects_unsafe_snapshots(kind):
    item, at = reviewed(), NOW
    if kind == "empty":
        items = []
    else:
        if kind == "sample":
            item = item.model_copy(update={"is_sample": True})
        elif kind == "stale":
            item = item.model_copy(update={"verified_at": NOW - timedelta(hours=25)})
        elif kind == "future":
            item = item.model_copy(update={"verified_at": NOW + timedelta(seconds=1)})
        elif kind == "naive":
            at = NOW.replace(tzinfo=None)
        items = [item]
    with pytest.raises(ValueError):
        directory_snapshot(items, at)


def test_export_order_is_deterministic():
    first = reviewed().model_copy(update={"id": "a"})
    second = reviewed().model_copy(update={"id": "z"})
    assert directory_snapshot([second, first], NOW) == directory_snapshot([first, second], NOW)


def test_failed_cli_export_preserves_existing_output(tmp_path):
    output = tmp_path / "directory.json"
    output.write_text("existing")
    process = subprocess.run([sys.executable, "-m", "app.export_directory",
                              "data/sample_resources.json", str(output)], capture_output=True)
    assert process.returncode != 0
    assert output.read_text() == "existing"


def test_cli_exports_valid_reviewed_snapshot(tmp_path):
    data = reviewed().model_copy(update={"verified_at": datetime.now(timezone.utc)})
    source, output = tmp_path / "input.json", tmp_path / "directory.json"
    source.write_text(json.dumps([data.model_dump(mode="json")]))
    process = subprocess.run([sys.executable, "-m", "app.export_directory", str(source), str(output)],
                             capture_output=True)
    assert process.returncode == 0
    assert json.loads(output.read_text())["schema_version"] == 1
