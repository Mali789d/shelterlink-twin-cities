"""The verified seed's append-only history must anchor the current seed.

data/verified_resources.history.jsonl records one operator review event per
seed change. If the seed changes without a history append, the anchor check
fails here - the seed can never silently drift from its review record. The
chain records review events only, never provider verification or publication.
"""
from pathlib import Path

from app.history import read_history, verify_history

REPO = Path(__file__).parent.parent
SEED = REPO / "data" / "verified_resources.json"
HISTORY = REPO / "data" / "verified_resources.history.jsonl"


def test_seed_history_anchors_the_current_seed():
    result = verify_history(HISTORY, SEED)
    assert result["chain_ok"], result["problems"]
    assert result["snapshot_matches_latest"] is True


def test_seed_history_records_are_explained_review_events():
    records = read_history(HISTORY)
    assert len(records) >= 1
    for record in records:
        assert record["note"].strip(), "every seed change needs an explaining note"
        assert record["resource_count"] >= 1
        assert isinstance(record["snapshot_sha256"], str)
        assert len(record["snapshot_sha256"]) == 64
