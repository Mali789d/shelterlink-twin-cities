"""Read-only review of provenance and freshness blockers, never launch approval."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .data import load_resources
from .freshness import DEFAULT_MAX_AGE, Freshness, resource_freshness
from .ingest import within_service_area
from .models import Resource

# Blockers only say the snapshot already failed. Operators also need advance
# notice: a record inside its last hours before the freshness limit still
# passes --check today and blocks the next export tomorrow. Six hours gives
# the review cadence time to re-check sources before the gate turns.
EXPIRING_SOON_WINDOW = timedelta(hours=6)


def audit_resources(resources, at: datetime) -> dict:
    """Report IDs only; do not disclose contact details or change verification dates."""
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("audit timestamp must include a timezone")
    checked = [Resource.model_validate(item.model_dump()) for item in resources]
    ids = [item.id for item in checked]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate resource IDs")
    sample, stale, future = [], [], []
    walk_in_only, no_hours, out_of_area, expiring = [], [], [], []
    now_utc = at.astimezone(timezone.utc)
    for item in checked:
        if item.is_sample:
            sample.append(item.id)
        if item.verified_at > at:
            future.append(item.id)
        elif resource_freshness(item, at) is Freshness.STALE:
            stale.append(item.id)
        elif (item.verified_at.astimezone(timezone.utc) + DEFAULT_MAX_AGE
                - now_utc) <= EXPIRING_SOON_WINDOW:
            # Currently valid, but the freshness limit is close: re-check the
            # source now instead of discovering the blocker after it lands.
            expiring.append(item.id)
        if item.phone is None and item.website is None:
            # No call or click route: the listing only helps someone who can walk in.
            walk_in_only.append(item.id)
        if not item.hours:
            no_hours.append(item.id)
        if not within_service_area(item.latitude, item.longitude):
            # Merged or hand-edited snapshots bypass ingestion's service-area
            # guard, so the review flags out-of-area listings here instead.
            out_of_area.append(item.id)
    passes = bool(checked) and not (sample or stale or future)
    # A fresh snapshot is only valid until its oldest record reaches the age limit.
    # Use UTC before adding the duration so a DST change cannot extend the window.
    deadline = min((item.verified_at.astimezone(timezone.utc) + DEFAULT_MAX_AGE
                    for item in checked), default=None) if passes else None
    return {
        "freshness_deadline": deadline.isoformat() if deadline else None,
        "freshness_seconds_remaining": (deadline - now_utc).total_seconds()
            if deadline else None,
        "expiring_soon_window_seconds": int(EXPIRING_SOON_WINDOW.total_seconds()),
        "notice": "Offline review only. Not provider verification, live availability or launch approval.",
        "as_of": at.isoformat(),
        "resource_count": len(checked),
        "blockers": {"empty": not checked, "sample_ids": sorted(sample),
                     "stale_ids": sorted(stale), "future_ids": sorted(future)},
        # Review warnings, not blockers: they never gate export validation, and
        # keys and values carry IDs only so no contact details leave the report.
        "warnings": {"walk_in_only_ids": sorted(walk_in_only),
                     "no_hours_ids": sorted(no_hours),
                     "out_of_area_ids": sorted(out_of_area),
                     "expiring_soon_ids": sorted(expiring)},
        "export_validation_passes": passes,
        "provider_verification_confirmed": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Audit directory blockers without writing or publishing")
    parser.add_argument("source", type=Path)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when export blockers exist; still print the complete JSON report")
    args = parser.parse_args()
    report = audit_resources(load_resources(args.source), datetime.now(timezone.utc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # Opt-in shell gate, not publication approval. Advisory warnings stay
    # advisory, and report-only callers retain the existing success exit.
    if args.check and not report["export_validation_passes"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
