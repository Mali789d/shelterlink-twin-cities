"""Produce a reviewed static-directory snapshot without paid infrastructure.

No export is evidence of live bed availability. Publication is a separate step.
"""
import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .data import MAX_SNAPSHOT_BYTES, load_resources
from .freshness import Freshness, resource_freshness
from .models import Resource

# The 211/911 notice is one wording across the exporter and every page module;
# tests/test_web_parity.py pins all copies equal.
DIRECTORY_NOTICE = "Directory information only. Call first; current local help: 211; emergency: 911."


def directory_snapshot(resources, at: datetime) -> dict:
    if at.tzinfo is None:
        raise ValueError("export timestamp must include a timezone")
    # Public callers may pass model_copy/model_construct objects that bypass validation.
    # Revalidate the complete set before examining provenance or emitting any fields.
    resources = [Resource.model_validate(item.model_dump()) for item in resources]
    ids = [item.id for item in resources]
    if len(ids) != len(set(ids)):
        raise ValueError("cannot export duplicate resource IDs")
    if not resources:
        raise ValueError("cannot export an empty directory")
    if any(item.is_sample for item in resources):
        raise ValueError("cannot publish sample resources")
    if any(resource_freshness(item, at) is not Freshness.CURRENT for item in resources):
        raise ValueError("cannot publish stale or future-dated resources")
    records = []
    for item in sorted(resources, key=lambda resource: resource.id):
        # Deliberately exclude hours, raw availability and computed open-now claims.
        records.append({
            "id": item.id, "name": item.name, "category": item.category.value,
            "address": item.address, "latitude": item.latitude, "longitude": item.longitude,
            "phone": item.phone, "website": str(item.website) if item.website else None,
            "source_name": item.source_name, "source_url": str(item.source_url),
            "verified_at": item.verified_at.isoformat(),
        })
    return {
        "schema_version": 1, "generated_at": at.isoformat(),
        "notice": DIRECTORY_NOTICE,
        "resources": records,
        "resources_sha256": resources_digest(records),
    }


def _canonical_export_json(value) -> str:
    """Canonical export text, byte-identical to web/export-integrity.mjs canonicalJson.

    Object keys sorted, no spaces, UTF-8, shortest round-trip numbers; integral
    floats render as integers because JavaScript has a single number type. The
    reader recomputes this exact form, so any drift between the two
    implementations fails every export rather than silently passing.
    """
    if value is None or isinstance(value, bool):
        return json.dumps(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers cannot be canonicalized")
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_canonical_export_json(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            json.dumps(key, ensure_ascii=False) + ":" + _canonical_export_json(item)
            for key, item in sorted(value.items())) + "}"
    raise ValueError("unsupported value in export canonical form")


# The exact field set exported below, shared with web/export-integrity.mjs
# EXPORT_RESOURCE_FIELDS: the digest covers only what the page may show, so
# injected availability/hours/open-now claims change nothing that renders.
EXPORT_RESOURCE_FIELDS = ("address", "category", "id", "latitude", "longitude",
                          "name", "phone", "source_name", "source_url", "verified_at",
                          "website")


def resources_digest(records) -> str:
    """SHA-256 over the canonical exported records; verified by the web reader.

    A consistency check, not a signature: anyone who can replace the export
    file can recompute it. What it catches is corruption and partial edits -
    a changed record with a stale digest never renders.
    """
    projected = []
    for item in records:
        if not isinstance(item, dict) or any(key not in item for key in EXPORT_RESOURCE_FIELDS):
            raise ValueError("export record misses a reviewed field")
        projected.append({key: item[key] for key in EXPORT_RESOURCE_FIELDS})
    return hashlib.sha256(_canonical_export_json(projected).encode("utf-8")).hexdigest()


def export_file(source: Path, output: Path) -> None:
    source, output = Path(source), Path(output)
    # An export omits operator-only fields. Never replace its own source snapshot,
    # even through relative paths, symlinks or an existing hard-link alias.
    if source.resolve() == output.resolve() or (output.exists() and source.samefile(output)):
        raise ValueError("export output must not replace the source snapshot")
    snapshot = directory_snapshot(load_resources(source), datetime.now(timezone.utc))
    text = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    # The browser reader enforces the same byte cap. Pretty-printing can expand
    # a valid compact source, so validate serialized UTF-8 bytes before writes.
    if len(text.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise ValueError("export exceeds directory byte limit")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         delete=False) as file:
            temporary = Path(file.name)
            file.write(text)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Validate and export a static directory (not publish it)")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export_file(args.source, args.output)


if __name__ == "__main__":
    main()
