"""Combine a base snapshot and a reviewed candidate into one validated snapshot.

Ingestion produces candidates and review compares snapshots; merging is the step
that actually applies reviewed records. A provider re-export must never silently
duplicate or overwrite directory entries, so ID conflicts are loud by default
and every applied replacement is listed by ID. A candidate identical to the base
record applies no change: it is reported as unchanged, not as a replacement, so
the reviewer never hunts for a phantom edit and no duplicate heuristic fires on
a record nothing happened to. Merging changes no record: each keeps its own
provenance and sample flag, and the output is review input for the existing
audit, history and export tools - not verification or publication.
"""
import argparse
import json
import os
import tempfile
from pathlib import Path

from .data import MAX_SNAPSHOT_BYTES, load_resources
from .duplicates import find_possible_duplicates
from .models import Resource
from .review_changes import compare_resources

POLICIES = ("reject", "replace", "keep")

NOTICE = "Merged snapshot is review input only. Not provider verification or publication approval."


def merge_resources(base, candidate, on_conflict="reject") -> dict:
    if on_conflict not in POLICIES:
        raise ValueError(f"conflict policy must be one of: {', '.join(POLICIES)}")
    # The file entry point validates snapshots, but direct callers can pass
    # generators, duplicate IDs, or model_copy objects that bypass validation.
    # Check each input before indexing: a dict would silently pick the last
    # duplicate candidate, even when "replace" only approved cross-input IDs.
    def checked(items, label):
        result = [Resource.model_validate(item.model_dump()) for item in items]
        ids = [item.id for item in result]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{label} snapshot contains duplicate IDs")
        return result

    base = checked(base, "base")
    candidate = checked(candidate, "candidate")
    base_ids = {resource.id for resource in base}
    conflicts = sorted({resource.id for resource in candidate} & base_ids)
    if conflicts and on_conflict == "reject":
        raise ValueError("candidate IDs already exist in the base snapshot: "
                         + ", ".join(conflicts))
    merged, replaced, skipped, unchanged = [], [], [], []
    candidate_by_id = {resource.id: resource for resource in candidate}
    for resource in base:
        update = candidate_by_id.get(resource.id)
        if update is not None and on_conflict == "replace":
            if update == resource:
                # Same content: nothing was applied, so this is not a replacement.
                unchanged.append(resource.id)
                merged.append(resource)
            else:
                merged.append(update)
                replaced.append(resource.id)
        else:
            merged.append(resource)
    added = []
    for resource in candidate:
        if resource.id not in base_ids:
            merged.append(resource)
            added.append(resource.id)
        elif on_conflict == "keep":
            skipped.append(resource.id)
    # Same-ID conflicts are loud, but a provider re-export can also carry the
    # same real-world site under a new ID. Flag heuristic look-alikes touching
    # the records this merge adds or replaces; the operator decides, the merge
    # never blocks on a heuristic. Pre-existing pairs stay out of this report.
    changed_ids = set(added) | set(replaced)
    introduced = [flag for flag in find_possible_duplicates(merged)["flags"]
                  if changed_ids & set(flag["ids"])]
    # Review the applied output, not the candidate: skipped and identical
    # records must not create warnings for changes this merge did not make.
    # Reuse the comparison rules so merge and standalone review cannot drift.
    review = compare_resources(base, merged)
    return {
        "notice": NOTICE,
        "on_conflict": on_conflict,
        "added": sorted(added),
        "replaced": sorted(replaced),
        "skipped": sorted(skipped),
        "unchanged": sorted(unchanged),
        "possible_duplicates": introduced,
        "verification_reviews": review["verification_reviews"],
        "regressions": review["regressions"],
        "resources": merged,
    }


def merge_files(base_path, candidate_path, output_path, on_conflict="reject") -> dict:
    base_path, candidate_path, output_path = (Path(base_path), Path(candidate_path),
                                              Path(output_path))
    # Never let the output replace an input, even through links or aliases.
    for source in (base_path, candidate_path):
        if source.resolve() == output_path.resolve() or (
                output_path.exists() and source.samefile(output_path)):
            raise ValueError("merge output must not replace an input snapshot")
    # Validate both inputs fully before the output path is touched.
    base = load_resources(base_path)
    candidate = load_resources(candidate_path)
    result = merge_resources(base, candidate, on_conflict)
    text = json.dumps([resource.model_dump(mode="json") for resource in result.pop("resources")],
                      ensure_ascii=False, indent=2) + "\n"
    if len(text.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise ValueError("merged snapshot exceeds byte limit")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=output_path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(text)
        os.replace(temporary, output_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    result["resource_count"] = len(base) + len(result["added"])
    result["output"] = str(output_path)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Merge a reviewed candidate into a base snapshot for further review")
    parser.add_argument("base", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--on-conflict", choices=POLICIES, default="reject",
                        help="reject (default) fails on duplicate IDs; replace applies changed "
                             "candidate records and lists them; keep retains the base record")
    args = parser.parse_args()
    print(json.dumps(merge_files(args.base, args.candidate, args.output, args.on_conflict),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
