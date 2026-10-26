"""Turn a raw provider export into a validated candidate snapshot for human review.

Importing real provider data (211, county or shelter exports) must not need ad-hoc
scripts. The operator supplies the provider's records plus an explicit field mapping;
every record is validated on its own, so one dirty row rejects itself with a reason
instead of failing the whole batch or slipping through unnoticed.

Nothing here verifies providers or promotes records: ``is_sample`` keeps the model's
safe default unless a record asserts it explicitly, and the candidate file feeds the
same offline review tools (audit, compare, export) as any other snapshot.
"""
import argparse
import csv
import io
import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from .data import MAX_SNAPSHOT_BYTES, unique_object
from .hours_text import parse_hours_text
from .models import Resource


def _read_json_array(path: Path, label: str):
    with Path(path).open("rb") as file:
        raw = file.read(MAX_SNAPSHOT_BYTES + 1)
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise ValueError(f"{label} exceeds byte limit")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    if not isinstance(data, list):
        raise ValueError(f"{label} must be a JSON array")
    return data


def _read_csv_records(path: Path, label: str):
    """CSV with a header row: the format county and 211 exports actually arrive in.

    Every value is text, so structured fields (coordinates, hours, booleans) face
    the same per-record validation as JSON - and ``is_sample`` can never be
    asserted from a CSV row. Structural problems fail the whole file loudly
    instead of guessing: duplicate or blank column names would silently drop a
    provider field, and a ragged row means a broken export.
    """
    with Path(path).open("rb") as file:
        raw = file.read(MAX_SNAPSHOT_BYTES + 1)
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise ValueError(f"{label} exceeds byte limit")
    # utf-8-sig strips the byte-order mark some spreadsheet exports carry.
    reader = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
    header = next(reader, None)
    if header is None:
        raise ValueError(f"{label} must be a CSV with a header row")
    if any(not column.strip() for column in header):
        raise ValueError(f"{label} has a blank column name")
    if len(header) != len(set(header)):
        raise ValueError(f"{label} has duplicate column names")
    records = []
    for line_number, row in enumerate(reader, start=2):
        if not row:  # a truly blank line is an export artifact, not a record
            continue
        if len(row) != len(header):
            raise ValueError(f"{label} row {line_number} has {len(row)} fields, "
                             f"expected {len(header)}")
        records.append(dict(zip(header, row)))
    if not records:
        raise ValueError(f"{label} has no records")
    return records


def read_provider_records(path: Path, label: str = "provider export"):
    """A provider export as records: JSON array, or CSV chosen by file extension."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return _read_csv_records(path, label)
    return _read_json_array(path, label)


def load_mapping(path: Path) -> dict[str, str]:
    with Path(path).open("rb") as file:
        mapping = json.loads(file.read(MAX_SNAPSHOT_BYTES + 1).decode("utf-8"),
                             object_pairs_hook=unique_object)
    if not isinstance(mapping, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in mapping.items()):
        raise ValueError("field mapping must be a JSON object of resource field: provider field")
    # A typo like "addres" must fail loudly instead of silently dropping addresses.
    unknown = sorted(set(mapping) - set(Resource.model_fields))
    if unknown:
        raise ValueError(f"mapping targets unknown resource fields: {', '.join(unknown)}")
    if not mapping:
        raise ValueError("field mapping must not be empty")
    return mapping


def ingest_records(raw_records, mapping: dict[str, str]) -> dict:
    """Validate provider records individually; a bad row never fails or joins the batch."""
    candidates: list[Resource] = []
    rejections: list[dict] = []
    seen_ids: set[str] = set()
    for index, record in enumerate(raw_records):
        label = f"record {index}"
        if not isinstance(record, dict):
            rejections.append({"index": index, "record_id": None,
                               "errors": ["record must be a JSON object"]})
            continue
        mapped = {target: record[source] for target, source in mapping.items() if source in record}
        if isinstance(mapped.get("hours"), str):
            # Provider exports carry hours as text; parse strictly or reject the record.
            try:
                mapped["hours"] = parse_hours_text(mapped["hours"])
            except ValueError as error:
                rejections.append({"index": index, "record_id": mapped.get("id"),
                                   "errors": [f"hours: {error}"]})
                continue
        try:
            resource = Resource.model_validate(mapped)
        except ValidationError as error:
            # Field and message only; provider values are not echoed into the report.
            rejections.append({"index": index, "record_id": mapped.get("id"),
                               "errors": [f"{'.'.join(str(part) for part in issue['loc'])}: "
                                          f"{issue['msg']}" for issue in error.errors()]})
            continue
        if resource.id in seen_ids:
            rejections.append({"index": index, "record_id": resource.id,
                               "errors": ["duplicate resource ID"]})
            continue
        seen_ids.add(resource.id)
        candidates.append(resource)
    return {"candidates": candidates, "rejections": rejections}


def write_candidate(resources: list[Resource], output: Path, inputs: list[Path]) -> None:
    """Write the candidate snapshot atomically; never overwrite any input file."""
    output = Path(output)
    for source in inputs:
        source = Path(source)
        if source.resolve() == output.resolve() or (output.exists() and source.samefile(output)):
            raise ValueError("candidate output must not replace an input file")
    text = json.dumps([item.model_dump(mode="json") for item in resources],
                      ensure_ascii=False, indent=2) + "\n"
    if len(text.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise ValueError("candidate snapshot exceeds byte limit")
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
    parser = argparse.ArgumentParser(
        description="Validate a provider export into a candidate snapshot for review")
    parser.add_argument("source", type=Path,
                        help="provider export: a JSON array of records, or a .csv with header row")
    parser.add_argument("mapping", type=Path, help="JSON object of resource field: provider field")
    parser.add_argument("output", type=Path, help="candidate snapshot path (reviewed separately)")
    args = parser.parse_args()
    mapping = load_mapping(args.mapping)
    report = ingest_records(read_provider_records(args.source), mapping)
    write_candidate(report["candidates"], args.output, [args.source, args.mapping])
    print(json.dumps({
        "notice": "Candidate only. Not provider verification or publication; review before use.",
        "candidate_count": len(report["candidates"]),
        "rejection_count": len(report["rejections"]),
        "rejections": report["rejections"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
