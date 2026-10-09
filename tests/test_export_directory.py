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


@pytest.mark.parametrize("update", [
    {"latitude": 91}, {"longitude": -181}, {"name": "   "},
    {"source_url": "javascript:alert(1)"}, {"verified_at": NOW.replace(tzinfo=None)},
    {"hours": {0: [("25:00", "26:00")]}}, {"category": "invalid"},
])
def test_export_revalidates_models_that_bypass_constructor_validation(update):
    item = reviewed().model_copy(update=update)
    with pytest.raises(ValueError):
        directory_snapshot([item], NOW)


def test_export_rejects_duplicate_ids_even_for_direct_callers():
    with pytest.raises(ValueError, match="duplicate"):
        directory_snapshot([reviewed(), reviewed()], NOW)


def test_export_rejects_ids_that_collide_after_normalization():
    with pytest.raises(ValueError, match="duplicate"):
        directory_snapshot([reviewed().model_copy(update={"id": "same"}),
                            reviewed().model_copy(update={"id": " same "})], NOW)


def test_export_accepts_generator_and_normalizes_valid_copied_fields():
    item = reviewed().model_copy(update={"name": " Fixture only "})
    result = directory_snapshot((value for value in [item]), NOW)
    assert result["resources"][0]["name"] == "Fixture only"
    assert item.name == " Fixture only "
