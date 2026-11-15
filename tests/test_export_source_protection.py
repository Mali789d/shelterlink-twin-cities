"""A directory export must never destroy the operator's source snapshot."""
import json
import os
from datetime import datetime, timezone

import pytest

from app.data import load_resources
from app.export_directory import export_file


def source_file(tmp_path):
    source = tmp_path / "source.json"
    item = load_resources()[0].model_copy(update={"is_sample": False,
        "verified_at": datetime.now(timezone.utc)})
    source.write_text(json.dumps([item.model_dump(mode="json")]))
    return source


@pytest.mark.parametrize("alias", ["same", "relative", "symlink", "hardlink"])
def test_source_aliases_are_rejected_without_writes(tmp_path, monkeypatch, alias):
    source = source_file(tmp_path)
    before = source.read_bytes()
    if alias == "same":
        output = source
    elif alias == "relative":
        monkeypatch.chdir(tmp_path)
        output = source.relative_to(tmp_path)
    else:
        output = tmp_path / "alias.json"
        if alias == "symlink":
            output.symlink_to(source)
        else:
            os.link(source, output)
    with pytest.raises(ValueError, match="source snapshot"):
        export_file(source, output)
    assert source.read_bytes() == before
    assert output.read_bytes() == before
    assert not list(tmp_path.glob("tmp*"))


def test_separate_export_preserves_source_and_replaces_old_output(tmp_path):
    source = source_file(tmp_path)
    before = source.read_bytes()
    output = tmp_path / "directory.json"
    output.write_text("old output")
    export_file(source, output)
    result = json.loads(output.read_text())
    assert result["schema_version"] == 1
    assert "is_sample" not in result["resources"][0]
    assert source.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["directory.json", "source.json"]


@pytest.mark.parametrize('alias', ['same', 'relative', 'symlink', 'hardlink'])
def test_history_aliases_are_rejected_without_writes(tmp_path, monkeypatch, alias):
    from app.history import append_record
    source = source_file(tmp_path)
    history = tmp_path / 'history.jsonl'
    append_record(history, source, 'reviewed fixture')
    if alias == 'same':
        output = history
    elif alias == 'relative':
        monkeypatch.chdir(tmp_path)
        output = 'history.jsonl'
    elif alias == 'symlink':
        output = tmp_path / 'alias.json'
        output.symlink_to(history)
    else:
        output = tmp_path / 'alias.json'
        os.link(history, output)
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError, match='change history'):
        export_file(source, output, history=history)
    assert {p: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_export_anchors_and_emits_one_loaded_snapshot_during_source_edit(tmp_path, monkeypatch):
    import app.export_directory as exporter
    from app.history import append_record
    source = source_file(tmp_path)
    history = tmp_path / 'history.jsonl'
    append_record(history, source, 'reviewed fixture')
    original = load_resources(source)
    real_load = exporter.load_resources
    calls = []

    def load_then_edit(path):
        calls.append(path)
        loaded = real_load(path)
        changed = loaded[0].model_copy(update={'name': 'Unreviewed concurrent edit'})
        source.write_text(json.dumps([changed.model_dump(mode='json')]))
        return loaded

    monkeypatch.setattr(exporter, 'load_resources', load_then_edit)
    output = tmp_path / 'export.json'
    export_file(source, output, history=history)
    assert calls == [source]
    exported = json.loads(output.read_text())
    assert exported['resources'][0]['name'] == original[0].name
    assert exported['review_sha256'] == json.loads(history.read_text())['snapshot_sha256']
    assert 'Unreviewed concurrent edit' not in output.read_text()


def test_history_gate_refusal_preserves_existing_output_and_inputs(tmp_path):
    from app.history import append_record
    source = source_file(tmp_path)
    history = tmp_path / 'history.jsonl'
    append_record(history, source, 'reviewed fixture')
    changed = load_resources(source)[0].model_copy(update={'name': 'Unrecorded change'})
    source.write_text(json.dumps([changed.model_dump(mode='json')]))
    output = tmp_path / 'export.json'
    output.write_text('previous export')
    before = {p: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError, match='does not anchor'):
        export_file(source, output, history=history)
    assert {p: p.read_bytes() for p in tmp_path.iterdir()} == before
