"""Never replace a usable directory with output the browser refuses to read."""
import json
from datetime import datetime, timezone

import pytest

import app.export_directory as exporter
from app.data import load_resources


@pytest.fixture
def setup_files(tmp_path):
    item = load_resources()[0].model_copy(update={"is_sample": False,
        "name": "Caawimo 🏠", "verified_at": datetime.now(timezone.utc)})
    source = tmp_path / "source.json"
    source.write_text(json.dumps([item.model_dump(mode="json")], ensure_ascii=False))
    output = tmp_path / "directory.json"
    return source, output


def test_oversize_output_keeps_previous_file_and_leaves_no_temporary(setup_files, monkeypatch):
    source, output = setup_files
    output.write_text("previous reviewed export")
    before = source.read_bytes()
    monkeypatch.setattr(exporter, "MAX_SNAPSHOT_BYTES", 1)
    with pytest.raises(ValueError, match="byte limit"):
        exporter.export_file(source, output)
    assert output.read_text() == "previous reviewed export"
    assert source.read_bytes() == before
    assert sorted(path.name for path in source.parent.iterdir()) == ["directory.json", "source.json"]


def test_oversize_output_does_not_create_destination(setup_files, monkeypatch):
    source, output = setup_files
    monkeypatch.setattr(exporter, "MAX_SNAPSHOT_BYTES", 1)
    with pytest.raises(ValueError, match="byte limit"):
        exporter.export_file(source, output)
    assert not output.exists()


def test_exact_utf8_byte_limit_succeeds_but_one_byte_less_rejects(setup_files, monkeypatch):
    source, output = setup_files
    clock = datetime.now(timezone.utc)
    class FixedDatetime:
        @staticmethod
        def now(tz):
            return clock
    monkeypatch.setattr(exporter, "datetime", FixedDatetime)
    exporter.export_file(source, output)
    contents = output.read_bytes()
    assert len(contents) > len(contents.decode("utf-8"))
    monkeypatch.setattr(exporter, "MAX_SNAPSHOT_BYTES", len(contents))
    exporter.export_file(source, output)
    assert output.read_bytes() == contents
    monkeypatch.setattr(exporter, "MAX_SNAPSHOT_BYTES", len(contents) - 1)
    with pytest.raises(ValueError, match="byte limit"):
        exporter.export_file(source, output)
    assert output.read_bytes() == contents
