"""Server-persisted pipeline state (queue + card states).

Lives in the data dir so the existing backup/restore covers it, and
mirrors app_settings.py (fresh read per call, tolerant of missing/corrupt).
All mutation goes through mutate_entries, which holds a lock across
load->modify->save: a lock around the write alone would still lose
updates (two callers both read [A], then write [A,B] and [A,C]).

Spec: docs/specs/2026-07-28-server-persisted-pipeline-state-spec.md
"""

import json
import os
import threading
from datetime import datetime, timedelta

from ..config import Config

_DEFAULT_PATH = os.path.join(Config.UPLOAD_FOLDER, "pipeline_state.json")
_LOCK = threading.Lock()

# 服务器保存的字段（不含文件字节：太大且属于浏览器本地）
SERVER_FIELDS = ("tmpId", "mode", "status", "simId", "projectId", "graphId",
                 "buildTaskId", "prompt", "fileName", "createdAt", "updatedAt")


def default_path() -> str:
    return _DEFAULT_PATH


def load_entries(path: str = None) -> list:
    """Read the entry list; a missing or corrupt file yields []."""
    try:
        with open(path or _DEFAULT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    entries = data.get("entries") if isinstance(data, dict) else data
    return entries if isinstance(entries, list) else []


def save_entries(path: str, entries: list) -> None:
    """Atomic write (temp file + os.replace) so a torn write never corrupts."""
    target = path or _DEFAULT_PATH
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = f"{target}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"entries": entries}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, target)


def upsert_entry(entries: list, entry: dict, now: datetime = None) -> list:
    """Replace-or-append by tmpId, stamping updatedAt. Pure."""
    now = now or datetime.now()
    clean = {k: entry.get(k) for k in SERVER_FIELDS if k in entry}
    clean["tmpId"] = entry.get("tmpId")
    clean["updatedAt"] = now.isoformat()
    out, replaced = [], False
    for e in entries:
        if e.get("tmpId") == clean["tmpId"]:
            out.append({**e, **clean})
            replaced = True
        else:
            out.append(e)
    if not replaced:
        out.append(clean)
    return out


def remove_entry(entries: list, tmp_id: str) -> list:
    """Drop one entry by tmpId. Pure."""
    return [e for e in entries if e.get("tmpId") != tmp_id]


def prune_entries(entries: list, now: datetime = None, ttl_hours: int = 24) -> list:
    """Drop finished entries and anything past the TTL. Pure."""
    now = now or datetime.now()
    cutoff = now - timedelta(hours=ttl_hours)
    out = []
    for e in entries:
        if e.get("status") in ("done", "failed"):
            continue
        try:
            updated = datetime.fromisoformat(e.get("updatedAt", ""))
        except (TypeError, ValueError):
            updated = now          # unparseable -> treat as fresh, never drop blindly
        if updated < cutoff:
            continue
        out.append(e)
    return out


# Run-record values that mean "this simulation is NOT running". `idle` counts:
# after a restart the record can be missing/reset, which is exactly the stale
# case that used to pin an entry on 'running' forever.
_NOT_RUNNING = ("completed", "stopped", "failed", "idle")


def reconcile_with_runs(entries: list, run_status_of) -> list:
    """Release entries whose simulation is no longer running. Pure.

    The browser driver owns an entry's status, so if that browser dies (tab
    closed, restart) the entry can sit on 'running' forever and hold the slot,
    blocking the queue. The simulation's own run record is ground truth.

    Only entries whose OWN status is 'running' are released: a pre-run stage
    ('preparing', 'creating', ...) legitimately has an idle run record because
    the run has not started yet.

    A MISSING record (None) also counts as not-running for a 'running' entry:
    if the driver said it started a run and no run record exists, the run is
    gone (restart wiped it). A false release self-corrects — the owning
    browser's entry is still dirty and re-POSTs on the next tick.
    """
    out = []
    for e in entries:
        sim_id = e.get("simId")
        rs = run_status_of(sim_id) if sim_id else "skip"
        if sim_id and e.get("status") == "running" and (rs is None or rs in _NOT_RUNNING):
            out.append({**e, "status": "done"})
        else:
            out.append(e)
    return out


def run_status_reader(run_state_dir: str):
    """Build a run_status_of(sim_id) that reads run_state.json from disk."""
    def _read(sim_id):
        try:
            with open(os.path.join(run_state_dir, sim_id, "run_state.json"),
                      "r", encoding="utf-8") as f:
                return json.load(f).get("runner_status")
        except (OSError, json.JSONDecodeError):
            return None
    return _read


def mutate_entries(path: str, fn) -> list:
    """Locked read-modify-write. The ONLY way handlers mutate the store."""
    with _LOCK:
        entries = fn(load_entries(path))
        save_entries(path, entries)
        return entries
