"""TDD: server-persisted pipeline state store."""
import threading
from datetime import datetime, timedelta

from app.utils.pipeline_state import (
    load_entries, save_entries, upsert_entry, remove_entry,
    prune_entries, mutate_entries,
)

NOW = datetime(2026, 7, 28, 12, 0, 0)


def _e(tid, status="queued", updated=None):
    return {"tmpId": tid, "status": status, "prompt": "p", "fileName": "f.docx",
            "updatedAt": (updated or NOW).isoformat()}


def test_load_missing_file_returns_empty(tmp_path):
    assert load_entries(str(tmp_path / "nope.json")) == []


def test_load_corrupt_file_returns_empty(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("not json", encoding="utf-8")
    assert load_entries(str(p)) == []


def test_save_load_round_trip(tmp_path):
    p = str(tmp_path / "s.json")
    save_entries(p, [_e("a")])
    assert [x["tmpId"] for x in load_entries(p)] == ["a"]


def test_upsert_appends_then_replaces():
    es = upsert_entry([], _e("a"), NOW)
    assert len(es) == 1
    es = upsert_entry(es, {**_e("a"), "status": "running"}, NOW)
    assert len(es) == 1 and es[0]["status"] == "running"


def test_upsert_stamps_updated_at_and_keeps_tmpid():
    es = upsert_entry([], {"tmpId": "a", "status": "queued"}, NOW)
    assert es[0]["tmpId"] == "a" and es[0]["updatedAt"] == NOW.isoformat()


def test_remove_entry():
    es = upsert_entry([], _e("a"), NOW)
    assert remove_entry(es, "a") == []
    assert remove_entry([], "missing") == []


def test_prune_drops_done_failed_and_stale():
    old = NOW - timedelta(hours=48)
    es = [_e("keep", "running"), _e("d", "done"), _e("f", "failed"),
          _e("stale", "queued", updated=old)]
    assert [x["tmpId"] for x in prune_entries(es, NOW, ttl_hours=24)] == ["keep"]


def test_mutate_entries_applies_fn_and_persists(tmp_path):
    p = str(tmp_path / "s.json")
    out = mutate_entries(p, lambda es: upsert_entry(es, _e("a"), NOW))
    assert [x["tmpId"] for x in out] == ["a"]
    assert [x["tmpId"] for x in load_entries(p)] == ["a"]


def test_mutate_entries_is_atomic_under_concurrency(tmp_path):
    # B12: two threads upserting DIFFERENT ids -> BOTH survive.
    # A lock wrapping only the write loses one (last-writer-wins).
    p = str(tmp_path / "s.json")
    barrier = threading.Barrier(2)

    def worker(tid):
        barrier.wait()
        for _ in range(20):
            mutate_entries(p, lambda es: upsert_entry(es, _e(tid), NOW))

    ts = [threading.Thread(target=worker, args=(t,)) for t in ("a", "b")]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert {x["tmpId"] for x in load_entries(p)} == {"a", "b"}
