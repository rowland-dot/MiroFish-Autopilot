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
PIPELINE_ACTIVE = ("ontology", "building", "creating", "preparing", "running", "reporting")

SERVER_FIELDS = ("tmpId", "mode", "status", "simId", "projectId", "graphId",
                 "buildTaskId", "reportId", "prompt", "fileName", "createdAt", "updatedAt",
                 "error")


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


# Defensive bound. Real capacity is 3 (1 active + 2 queued); this only stops a
# buggy or looping client from growing the file without limit.
MAX_ENTRIES = 20


def prune_entries(entries: list, now: datetime = None, ttl_hours: int = 24) -> list:
    """Drop finished entries and anything past the TTL, capped. Pure."""
    now = now or datetime.now()
    cutoff = now - timedelta(hours=ttl_hours)
    out = []
    for e in entries:
        # 'done' is superseded by the real history record; 'failed' stays
        # visible (with its error) until the user deletes it or TTL passes --
        # a silently vanishing failed card loses the user's job and the reason
        if e.get("status") == "done":
            continue
        try:
            updated = datetime.fromisoformat(e.get("updatedAt", ""))
        except (TypeError, ValueError):
            updated = now          # unparseable -> treat as fresh, never drop blindly
        if updated < cutoff:
            continue
        out.append(e)
    if len(out) <= MAX_ENTRIES:
        return out
    # 超容量时绝不能挤掉活跃条目——按位置截断曾把在跑的任务从守卫视野里挤掉
    active = [e for e in out if e.get("status") in PIPELINE_ACTIVE]
    rest = [e for e in out if e.get("status") not in PIPELINE_ACTIVE]
    keep_rest = max(0, MAX_ENTRIES - len(active))
    kept = set(id(e) for e in active) | set(id(e) for e in rest[-keep_rest:])
    return [e for e in out if id(e) in kept]


# 浏览器死掉后，ontology..reporting 阶段的条目会永远卡在活跃态：
# 既挡住部署闸门，又占着槽位。3 小时无更新即判定驱动方已消失，翻成
# 可见的 failed 卡片（不删除——静默消失会弄丢用户的任务与原因）。
_STALE_ACTIVE_SECONDS = 3 * 3600
_EXPIRABLE = ("ontology", "building", "creating", "preparing", "reporting")


def expire_stale_active(entries: list, now: datetime = None) -> list:
    now = now or datetime.now()
    out = []
    for e in entries:
        if e.get("status") in _EXPIRABLE:
            try:
                age = (now - datetime.fromisoformat(e.get("updatedAt", ""))).total_seconds()
            except (TypeError, ValueError):
                age = 0          # 时间戳不可解析：当作新鲜，绝不盲目失效
            if age > _STALE_ACTIVE_SECONDS:
                out.append({**e, "status": "failed",
                            "error": "浏览器会话中断，任务已失效（超过 3 小时无进展）"})
                continue
        out.append(e)
    return out


# Run-record values that mean "this simulation is NOT running". `idle` counts:
# after a restart the record can be missing/reset, which is exactly the stale
# case that used to pin an entry on 'running' forever.
_NOT_RUNNING = ("completed", "stopped", "failed", "idle")


# 终态后的宽限期：run 刚停止时，浏览器驱动器可能正要把条目推进到
# reporting——立刻释放会把条目从它手里删掉（先释放后推送的竞态）。
_RELEASE_GRACE_SECONDS = 300


def reconcile_with_runs(entries: list, run_status_of, now: datetime = None) -> list:
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
    now = now or datetime.now()
    out = []
    for e in entries:
        sim_id = e.get("simId")
        rec = run_status_of(sim_id) if sim_id else "skip"
        # reader may return a plain status string (legacy) or
        # {"status": ..., "ended_at": ...} (grace-aware)
        if isinstance(rec, dict):
            rs, ended_at = rec.get("status"), rec.get("ended_at")
        else:
            rs, ended_at = rec, None
        terminal = rs is None or rs in _NOT_RUNNING
        if sim_id and e.get("status") == "running" and terminal:
            # terminal WITH a fresh end timestamp: hold for the grace window so
            # the driver can carry the entry into its reporting stage
            if ended_at:
                try:
                    age = (now - datetime.fromisoformat(ended_at)).total_seconds()
                except (TypeError, ValueError):
                    age = _RELEASE_GRACE_SECONDS
                if age < _RELEASE_GRACE_SECONDS:
                    out.append(e)
                    continue
            out.append({**e, "status": "done"})
        else:
            out.append(e)
    return out


def run_status_reader(run_state_dir: str):
    """Build a run_status_of(sim_id) that reads run_state.json from disk."""
    def _read(sim_id):
        path = os.path.join(run_state_dir, sim_id, "run_state.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
        except OSError:
            return None                      # 文件不存在：run 确实没了
        except json.JSONDecodeError:
            # 写入方非原子（每 ~2s 覆写一次）；读到半截文件不等于 run 消失，
            # 零宽限地释放会把在跑的任务条目直接删掉
            return {"status": "unreadable", "ended_at": None}
        ended = d.get("completed_at") or d.get("updated_at")
        if not ended:
            try:
                ended = datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
            except OSError:
                ended = None
        return {"status": d.get("runner_status"), "ended_at": ended}
    return _read


def mutate_entries(path: str, fn) -> list:
    """Locked read-modify-write. The ONLY way handlers mutate the store."""
    with _LOCK:
        entries = fn(load_entries(path))
        save_entries(path, entries)
        return entries
