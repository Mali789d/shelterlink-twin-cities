"""Produce a reviewed static-directory snapshot without paid infrastructure.

No export is evidence of live bed availability. Publication is a separate step.
"""
import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .data import load_resources
from .freshness import Freshness, resource_freshness
from .models import Resource


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
        "notice": "Directory information only. Call first; current local help: 211; emergency: 911.",
        "resources": records,
    }


def main():
    parser = argparse.ArgumentParser(description="Validate and export a static directory (not publish it)")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    # Complete validation before touching output, so failed refreshes cannot truncate it.
    snapshot = directory_snapshot(load_resources(args.source), datetime.now(timezone.utc))
    text = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output.parent,
                                         delete=False) as file:
            temporary = Path(file.name)
            file.write(text)
        os.replace(temporary, args.output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
