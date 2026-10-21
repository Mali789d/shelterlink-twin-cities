"""Flag possible duplicate resources for human review - never merge them.

Real provider exports (211, county, city) overlap heavily, so a merged directory
needs more than the exact-ID deduplication in merge.py. These flags are
deterministic review hints only: they catch formatting drift (the same phone in
two layouts, the same name with different punctuation, coordinates inside one
building), not naming variants, and they never pick a winner. Every flag names
record IDs and the rules that fired - no contact details leave the snapshot.
"""
import argparse
import json
import re
from pathlib import Path

from .data import load_resources
from .search import distance_miles

NOTICE = ("Possible-duplicate review flags only. Not merge approval, "
          "provider verification, or publication.")
SAME_BUILDING_MILES = 25 / 1609.344  # 25 meters


def normalized_phone(phone: str | None) -> str | None:
    """Digits before any extension, without a US country-code prefix."""
    if phone is None:
        return None
    base = re.split(r" ?(?:x|ext\.?) ?[0-9]{1,6}$", phone)[0]
    digits = re.sub(r"\D", "", base)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits or None


def normalized_name(name: str) -> str:
    """Lowercase alphanumerics only - catches punctuation and spacing drift."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def find_possible_duplicates(resources) -> dict:
    """Pair up records that share a phone, a name, or a building's coordinates."""
    flags = []
    ordered = sorted(resources, key=lambda item: item.id)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            rules = []
            left_phone, right_phone = (normalized_phone(left.phone),
                                       normalized_phone(right.phone))
            if left_phone and left_phone == right_phone:
                rules.append("same_phone")
            if normalized_name(left.name) == normalized_name(right.name):
                rules.append("same_name")
            if distance_miles(left.latitude, left.longitude,
                              right.latitude, right.longitude) <= SAME_BUILDING_MILES:
                rules.append("same_location")
            if rules:
                flags.append({"ids": [left.id, right.id], "rules": rules})
    return {
        "notice": NOTICE,
        "resource_count": len(ordered),
        "flag_count": len(flags),
        "flags": flags,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Flag possible duplicate resources for review without changing anything")
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    print(json.dumps(find_possible_duplicates(load_resources(args.source)),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
