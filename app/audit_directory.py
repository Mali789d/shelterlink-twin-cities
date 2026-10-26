"""Read-only review of provenance and freshness blockers, never launch approval."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .data import load_resources
from .freshness import DEFAULT_MAX_AGE, Freshness, resource_freshness
from .models import Resource


def audit_resources(resources, at: datetime) -> dict:
    """Report IDs only; do not disclose contact details or change verification dates."""
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("audit timestamp must include a timezone")
    checked = [Resource.model_validate(item.model_dump()) for item in resources]
    ids = [item.id for item in checked]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate resource IDs")
    sample, stale, future = [], [], []
    walk_in_only, no_hours = [], []
    for item in checked:
        if item.is_sample:
            sample.append(item.id)
        if item.verified_at > at:
            future.append(item.id)
        elif resource_freshness(item, at) is Freshness.STALE:
            stale.append(item.id)
        if item.phone is None and item.website is None:
            # No call or click route: the listing only helps someone who can walk in.
            walk_in_only.append(item.id)
        if not item.hours:
            no_hours.append(item.id)
    passes = bool(checked) and not (sample or stale or future)
    # A fresh snapshot is only valid until its oldest record reaches the age limit.
    # Use UTC before adding the duration so a DST change cannot extend the window.
    deadline = min((item.verified_at.astimezone(timezone.utc) + DEFAULT_MAX_AGE
                    for item in checked), default=None) if passes else None
    return {
        "freshness_deadline": deadline.isoformat() if deadline else None,
        "freshness_seconds_remaining": (deadline - at.astimezone(timezone.utc)).total_seconds()
            if deadline else None,
        "notice": "Offline review only. Not provider verification, live availability or launch approval.",
        "as_of": at.isoformat(),
        "resource_count": len(checked),
        "blockers": {"empty": not checked, "sample_ids": sorted(sample),
                     "stale_ids": sorted(stale), "future_ids": sorted(future)},
        # Review warnings, not blockers: they never gate export validation, and
        # keys and values carry IDs only so no contact details leave the report.
        "warnings": {"walk_in_only_ids": sorted(walk_in_only),
                     "no_hours_ids": sorted(no_hours)},
        "export_validation_passes": passes,
        "provider_verification_confirmed": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Audit directory blockers without writing or publishing")
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_resources(load_resources(args.source), datetime.now(timezone.utc)),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
