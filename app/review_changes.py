"""Compare validated directory snapshots for human review, without publishing them."""
import argparse
import json
from pathlib import Path

from .data import load_resources
from .models import Resource


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
    for identity in sorted(old.keys() & new.keys()):
        fields = sorted(key for key in old[identity] if old[identity][key] != new[identity][key])
        if fields:
            changes.append({"id": identity, "fields": fields})
    return {
        "notice": "Change review only. Not provider verification or publication approval.",
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(old.keys() - new.keys()),
        "changed": changes,
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
