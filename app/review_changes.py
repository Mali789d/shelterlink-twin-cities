"""Compare validated directory snapshots for human review, without publishing them."""
import argparse
import json
from datetime import datetime
from pathlib import Path

from .data import load_resources
from .models import Resource


def _instant(iso_text: str) -> datetime:
    # Snapshots serialize UTC as a trailing Z, which Python 3.10 cannot parse.
    return datetime.fromisoformat(iso_text.replace("Z", "+00:00"))


def compare_resources(before, after):
    def indexed(items):
        result = {}
        for item in items:
            resource = Resource.model_validate(item.model_dump())
            if resource.id in result:
                raise ValueError("duplicate resource IDs")
            result[resource.id] = resource.model_dump(mode="json")
        return result

    old, new = indexed(before), indexed(after)
    changes = []
    regressions = []
    for identity in sorted(old.keys() & new.keys()):
        fields = sorted(key for key in old[identity] if old[identity][key] != new[identity][key])
        if not fields:
            continue
        changes.append({"id": identity, "fields": fields})
        # A provider re-export can quietly strip data. Call out the changes a
        # reviewer must not miss: contact channels or hours that disappeared, a
        # verification date that moved backwards, or a record sent back to sample.
        # Field names and booleans only - values never leave the snapshots.
        lost_fields = sorted(field for field in ("phone", "website", "hours")
                             if old[identity][field] and not new[identity][field])
        moved_backwards = (_instant(new[identity]["verified_at"])
                           < _instant(old[identity]["verified_at"]))
        returned_to_sample = not old[identity]["is_sample"] and new[identity]["is_sample"]
        if lost_fields or moved_backwards or returned_to_sample:
            regressions.append({"id": identity,
                                "lost_fields": lost_fields,
                                "returned_to_sample": returned_to_sample,
                                "verification_moved_backwards": moved_backwards})
    return {
        "notice": "Change review only. Not provider verification or publication approval.",
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(old.keys() - new.keys()),
        "changed": changes,
        "regressions": regressions,
        "unchanged_count": len(old.keys() & new.keys()) - len(changes),
    }


def main():
    parser = argparse.ArgumentParser(description="Review resource changes without publishing")
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare_resources(load_resources(args.before), load_resources(args.after)),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
