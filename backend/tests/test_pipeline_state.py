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


def test_prune_drops_done_and_stale_but_keeps_failed():
    # failed entries stay visible (with their error) until the user deletes
    # them or the TTL passes -- silently vanishing cards lose the user's job
    old = NOW - timedelta(hours=48)
    es = [_e("keep", "running"), _e("d", "done"), _e("f", "failed"),
          _e("stale", "queued", updated=old), _e("fstale", "failed", updated=old)]
    assert [x["tmpId"] for x in prune_entries(es, NOW, ttl_hours=24)] == ["keep", "f"]


def test_error_field_round_trips_through_upsert():
    es = upsert_entry([], {**_e("a", "failed"), "error": "LLM provider request failed (HTTP 429)"}, NOW)
    assert es[0]["error"] == "LLM provider request failed (HTTP 429)"


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


def test_reconcile_with_runs_marks_finished_sims_done():
    # A pipeline entry whose simulation already finished (or was killed) must
    # not keep holding the slot forever.
    from app.utils.pipeline_state import reconcile_with_runs
    entries = [
        {"tmpId": "a", "status": "running", "simId": "sim_dead"},
        {"tmpId": "b", "status": "running", "simId": "sim_live"},
        {"tmpId": "c", "status": "queued", "simId": None},
    ]
    status_of = {"sim_dead": "stopped", "sim_live": "running"}.get
    out = reconcile_with_runs(entries, status_of)
    assert out[0]["status"] == "done"        # finished -> released
    assert out[1]["status"] == "running"     # still alive -> untouched
    assert out[2]["status"] == "queued"      # no sim yet -> untouched


def test_reconcile_with_runs_leaves_entries_without_a_sim_alone():
    # no simId yet (pre-create) -> nothing to reconcile against
    from app.utils.pipeline_state import reconcile_with_runs
    entries = [{"tmpId": "a", "status": "running", "simId": None}]
    assert reconcile_with_runs(entries, lambda s: None)[0]["status"] == "running"


def test_reconcile_releases_running_entry_when_sim_is_idle():
    # After a restart the run record can be gone/idle: no live run, so a
    # pipeline entry still claiming 'running' is stale and must be released,
    # otherwise it holds the slot forever.
    from app.utils.pipeline_state import reconcile_with_runs
    entries = [{"tmpId": "a", "status": "running", "simId": "sim_x"}]
    assert reconcile_with_runs(entries, lambda s: "idle")[0]["status"] == "done"


def test_reconcile_does_not_release_pre_run_stages_on_idle():
    # 'preparing' with an idle run record is NORMAL (the run has not started).
    from app.utils.pipeline_state import reconcile_with_runs
    entries = [{"tmpId": "a", "status": "preparing", "simId": "sim_x"}]
    assert reconcile_with_runs(entries, lambda s: "idle")[0]["status"] == "preparing"


def test_reconcile_releases_running_entry_when_record_is_missing():
    # A 'running' entry with NO run record means the run is gone (a restart
    # wiped it) -> release, else it pins the slot forever. Safe: the owning
    # browser is still dirty and re-POSTs if it really is alive.
    from app.utils.pipeline_state import reconcile_with_runs
    entries = [{"tmpId": "a", "status": "running", "simId": "sim_x"}]
    assert reconcile_with_runs(entries, lambda s: None)[0]["status"] == "done"


def test_reconcile_keeps_pre_run_entry_with_missing_record():
    from app.utils.pipeline_state import reconcile_with_runs
    entries = [{"tmpId": "a", "status": "building", "simId": "sim_x"}]
    assert reconcile_with_runs(entries, lambda s: None)[0]["status"] == "building"


def test_prune_caps_total_entries(tmp_path):
    # Defensive bound: a looping/buggy client must not grow the file forever.
    from app.utils.pipeline_state import prune_entries, MAX_ENTRIES
    now = NOW
    many = [{"tmpId": f"t{i}", "status": "queued", "updatedAt": now.isoformat()}
            for i in range(MAX_ENTRIES + 10)]
    out = prune_entries(many, now)
    assert len(out) == MAX_ENTRIES
    # keeps the most recent, drops the oldest
    assert out[-1]["tmpId"] == f"t{MAX_ENTRIES + 9}"


def test_reconcile_grace_keeps_recently_stopped_run():
    # A run that JUST went terminal may be mid-handoff to the driver's
    # reporting stage — releasing instantly deletes the entry out from under
    # it (2026-07-29 incident). Terminal + young => keep.
    from app.utils.pipeline_state import reconcile_with_runs
    entries = [{"tmpId": "a", "status": "running", "simId": "sim_1"}]
    rec = {"status": "stopped", "ended_at": (NOW - timedelta(seconds=30)).isoformat()}
    out = reconcile_with_runs(entries, lambda s: rec, now=NOW)
    assert out[0]["status"] == "running"


def test_reconcile_releases_stopped_run_after_grace():
    from app.utils.pipeline_state import reconcile_with_runs
    entries = [{"tmpId": "a", "status": "running", "simId": "sim_1"}]
    rec = {"status": "stopped", "ended_at": (NOW - timedelta(minutes=10)).isoformat()}
    out = reconcile_with_runs(entries, lambda s: rec, now=NOW)
    assert out[0]["status"] == "done"


def test_reconcile_still_releases_missing_record_immediately():
    from app.utils.pipeline_state import reconcile_with_runs
    entries = [{"tmpId": "a", "status": "running", "simId": "sim_1"}]
    assert reconcile_with_runs(entries, lambda s: None, now=NOW)[0]["status"] == "done"


def test_reconcile_backwards_compatible_with_plain_string_reader():
    from app.utils.pipeline_state import reconcile_with_runs
    entries = [{"tmpId": "a", "status": "running", "simId": "sim_1"}]
    assert reconcile_with_runs(entries, lambda s: "stopped", now=NOW)[0]["status"] == "done"
