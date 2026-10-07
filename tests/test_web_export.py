"""Check the Python exporter and JavaScript reader against the same real schema."""
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.data import load_resources
from app.export_directory import directory_snapshot


def test_export_is_readable_by_browser_module(tmp_path):
    if not shutil.which("node"):
        pytest.skip("Node is required for browser-module integration tests")
    now = datetime.now(timezone.utc)
    item = load_resources()[0].model_copy(update={"is_sample": False, "verified_at": now})
    path = tmp_path / "directory.json"
    path.write_text(json.dumps(directory_snapshot([item], now)))
    module = Path("web/directory.mjs").resolve().as_uri()
    script = f'''import {{readDirectory}} from {json.dumps(module)};
import fs from 'node:fs';
const snapshot = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
const directory = readDirectory(snapshot);
if (directory.resources.length !== 1) process.exit(1);
if ('availability' in directory.resources[0]) process.exit(1);
'''
    result = subprocess.run(["node", "--input-type=module", "-e", script, str(path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
