"""Only an explicit JSON boolean may assert sample versus reviewed provenance."""
import json
from datetime import datetime, timezone

import pytest

from app.audit_directory import audit_resources
from app.data import DATA_PATH, load_resources
from app.export_directory import directory_snapshot
from app.models import Resource
from app.readiness import readiness_checks

AT = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("marker", ["false", "False", "true", "0", "1", "off", "no", 0, 1, None])
def test_coercible_or_null_markers_never_promote_a_record(marker, tmp_path):
    data = json.loads(DATA_PATH.read_text())[0]
    data["is_sample"] = marker
    path = tmp_path / "resources.json"
    path.write_text(json.dumps([data]))
    with pytest.raises(ValueError):
        load_resources(path)


@pytest.mark.parametrize("marker", [True, False])
def test_real_booleans_preserve_explicit_intent(marker):
    data = json.loads(DATA_PATH.read_text())[0]
    data["is_sample"] = marker
    assert Resource.model_validate(data).is_sample is marker


def test_missing_marker_remains_sample():
    data = json.loads(DATA_PATH.read_text())[0]
    data.pop("is_sample")
    assert Resource.model_validate(data).is_sample is True


@pytest.mark.parametrize("marker", [0, "false"])
def test_copied_invalid_markers_fail_export_audit_and_readiness(marker):
    item = load_resources()[0].model_copy(update={"is_sample": marker, "verified_at": AT})
    with pytest.raises(ValueError):
        directory_snapshot([item], AT)
    with pytest.raises(ValueError):
        audit_resources([item], AT)
    checks = readiness_checks([item], object(), {}, AT)
    assert not checks["verified_resource_snapshot"]
    assert not checks["current_resource_snapshot"]
