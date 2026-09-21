import json
from pathlib import Path

from .models import Resource

DATA_PATH = Path(__file__).parent.parent / "data" / "sample_resources.json"


def load_resources() -> list[Resource]:
    with DATA_PATH.open() as resource_file:
        return [Resource.model_validate(item) for item in json.load(resource_file)]
