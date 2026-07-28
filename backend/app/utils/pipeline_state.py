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


def mutate_entries(path: str, fn) -> list:
    """Locked read-modify-write. The ONLY way handlers mutate the store."""
    with _LOCK:
        entries = fn(load_entries(path))
        save_entries(path, entries)
        return entries
