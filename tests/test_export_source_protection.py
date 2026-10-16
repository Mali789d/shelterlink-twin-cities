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
