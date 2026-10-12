"""Validate a whole resource snapshot before exposing any records."""
import json
import os
from pathlib import Path

from .models import Resource

MAX_SNAPSHOT_BYTES = 1024 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("resource snapshot contains duplicate JSON keys")
        result[key] = value
    return result


DATA_PATH = Path(__file__).parent.parent / "data" / "sample_resources.json"


def load_resources(path: str | Path | None = None) -> list[Resource]:
    selected = Path(path or os.environ.get("SHELTERLINK_DATA_PATH") or DATA_PATH)
    # Bound actual bytes rather than trusting metadata; decoding never repairs bad UTF-8.
    with selected.open("rb") as resource_file:
        raw = resource_file.read(MAX_SNAPSHOT_BYTES + 1)
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise ValueError("resource snapshot exceeds byte limit")
    snapshot = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    if not isinstance(snapshot, list):
        raise ValueError("resource snapshot must be a JSON array")
    resources = [Resource.model_validate(item) for item in snapshot]
    ids = [resource.id for resource in resources]
    if len(ids) != len(set(ids)):
        raise ValueError("resource snapshot contains duplicate IDs")
    return resources
