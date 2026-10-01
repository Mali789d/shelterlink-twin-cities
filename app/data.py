"""Validate a whole resource snapshot before exposing any records."""
import json
import os
from pathlib import Path

from .models import Resource

DATA_PATH = Path(__file__).parent.parent / "data" / "sample_resources.json"


def load_resources(path: str | Path | None = None) -> list[Resource]:
    selected = Path(path or os.environ.get("SHELTERLINK_DATA_PATH") or DATA_PATH)
    with selected.open() as resource_file:
        snapshot = json.load(resource_file)
    if not isinstance(snapshot, list):
        raise ValueError("resource snapshot must be a JSON array")
    resources = [Resource.model_validate(item) for item in snapshot]
    ids = [resource.id for resource in resources]
    if len(ids) != len(set(ids)):
        raise ValueError("resource snapshot contains duplicate IDs")
    return resources
