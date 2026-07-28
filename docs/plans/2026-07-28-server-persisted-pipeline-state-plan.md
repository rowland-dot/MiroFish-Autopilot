# Server-Persisted Pipeline State — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Give the pipeline queue + card states a server-side home so they survive refresh/deploy/tabs and stay in sync with the backend — while adding ~zero upstream merge cost.

**Architecture:** A standalone JSON store in the data dir (`pipeline_state.json`, same pattern as `app_settings.json`, covered by the existing backup) behind a new `/api/pipeline` blueprint; all mutation through ONE locked read-modify-write entry point. The frontend keeps its driver browser-side (so upstream files stay untouched) and adds a sync layer: localStorage keeps the file bytes, the server owns status/membership, and a **pure** `mergeServerEntries` reconciles them (union-by-tmpId, dirty-local-wins, field-union, delete tombstones).

**Tech Stack:** Python/Flask + pytest; Vue 3 + `node --test`. Spec: `docs/specs/2026-07-28-server-persisted-pipeline-state-spec.md`. venv: `backend/.venv/Scripts/python.exe`.

**Upstream-cost budget:** 3 new files + 2 lines in the already-diverged `backend/app/__init__.py`. **No edits** to `simulation_runner.py`, `simulation.py`, `graph.py`, `report.py`.

**Baseline (verify before starting):** backend `252 passed`, frontend `40 passed`.

---

## File structure

**Create:** `backend/app/utils/pipeline_state.py`, `backend/app/api/pipeline.py`, `backend/tests/test_pipeline_state.py`, `backend/tests/test_pipeline_api.py`, `frontend/src/api/pipeline.js`, `frontend/tests/pipelineSync.test.mjs`, `frontend/tests/pipelineStore.test.mjs`

**Modify:** `backend/app/__init__.py` (2 lines), `frontend/src/store/pipelineQueue.js`, `frontend/src/services/pipelineDriver.js`

---

## Task 0: branch

The repo is currently on `main`; every task below commits, so branch first.

- [ ] **Step 1:** Ask the user for the branch name (a safety hook blocks agent-created branches) — suggested `feat/pipeline-state-sync`, base `main`.
- [ ] **Step 2:** `git checkout -b <name>` and record the base SHA: `git rev-parse main` (needed by Task 8's upstream-budget check).

---

## Task 1: pipeline_state pure ops + locked mutate (TDD)

**Files:** Create `backend/app/utils/pipeline_state.py`, `backend/tests/test_pipeline_state.py`

- [ ] **Step 1: Write failing tests**

```python
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
    p = tmp_path / "s.json"; p.write_text("not json", encoding="utf-8")
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
    [t.start() for t in ts]; [t.join() for t in ts]
    assert {x["tmpId"] for x in load_entries(p)} == {"a", "b"}
```

- [ ] **Step 2: Run → FAIL** — `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_pipeline_state.py -q`

- [ ] **Step 3: Implement**

```python
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
            out.append({**e, **clean}); replaced = True
        else:
            out.append(e)
    if not replaced:
        out.append(clean)
    return out


def remove_entry(entries: list, tmp_id: str) -> list:
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
            updated = now
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
```

- [ ] **Step 4: Run → PASS** (9 tests)
- [ ] **Step 5: Commit** — `git add backend/app/utils/pipeline_state.py backend/tests/test_pipeline_state.py && git commit -m "feat: pipeline_state store (pure ops + locked read-modify-write)"`

---

## Task 2: /api/pipeline blueprint (TDD)

**Files:** Create `backend/app/api/pipeline.py`, `backend/tests/test_pipeline_api.py`

- [ ] **Step 1: Write failing tests** (mirrors `test_settings_api.py`; `default_path()` reads the module global at call time so the monkeypatch reaches it)

```python
"""TDD: GET/POST/DELETE /api/pipeline."""
import pytest
from flask import Flask

import app.utils.pipeline_state as ps
from app.api.pipeline import pipeline_bp


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_DEFAULT_PATH", str(tmp_path / "pipeline_state.json"))
    app = Flask(__name__)
    app.register_blueprint(pipeline_bp, url_prefix="/api/pipeline")
    return app.test_client()


def test_get_empty(client):
    r = client.get("/api/pipeline")
    assert r.status_code == 200 and r.get_json()["data"]["entries"] == []


def test_post_then_get(client):
    client.post("/api/pipeline", json={"tmpId": "a", "status": "queued", "prompt": "p"})
    entries = client.get("/api/pipeline").get_json()["data"]["entries"]
    assert [e["tmpId"] for e in entries] == ["a"]


def test_post_upserts_not_duplicates(client):
    client.post("/api/pipeline", json={"tmpId": "a", "status": "queued"})
    r = client.post("/api/pipeline", json={"tmpId": "a", "status": "running"})
    entries = r.get_json()["data"]["entries"]
    assert len(entries) == 1 and entries[0]["status"] == "running"


def test_post_requires_tmpid(client):
    assert client.post("/api/pipeline", json={"status": "queued"}).status_code == 400


def test_delete_removes(client):
    client.post("/api/pipeline", json={"tmpId": "a", "status": "queued"})
    r = client.delete("/api/pipeline/a")
    assert r.status_code == 200 and r.get_json()["data"]["entries"] == []


def test_delete_unknown_id_is_ok(client):
    assert client.delete("/api/pipeline/nope").status_code == 200   # idempotent ack


def test_get_prunes_and_persists(client):
    client.post("/api/pipeline", json={"tmpId": "d", "status": "done"})
    assert client.get("/api/pipeline").get_json()["data"]["entries"] == []
    assert ps.load_entries(ps._DEFAULT_PATH) == []      # prune was persisted
```

- [ ] **Step 2: Run → FAIL**

- [ ] **Step 3: Implement**

```python
"""流水线状态 API：队列与卡片状态的服务器端存储。

独立蓝图，不改动上游文件（fork 需频繁与 upstream 同步）。
位于 /api/ 下，自动继承访问口令门（app 级 before_request，见 auth.py）。

Spec: docs/specs/2026-07-28-server-persisted-pipeline-state-spec.md
"""

from flask import Blueprint, jsonify, request

from ..utils.pipeline_state import (
    default_path, mutate_entries, prune_entries, remove_entry, upsert_entry,
)

pipeline_bp = Blueprint('pipeline', __name__)


def _ok(entries):
    return jsonify({"success": True, "data": {"entries": entries}})


@pipeline_bp.route('', methods=['GET'], strict_slashes=False)
def get_pipeline():
    """读取条目（顺带清理并落盘，避免只读时文件无限增长）。"""
    return _ok(mutate_entries(default_path(), lambda es: prune_entries(es)))


@pipeline_bp.route('', methods=['POST'], strict_slashes=False)
def upsert_pipeline():
    """新增/更新一条（按 tmpId）。"""
    entry = request.get_json(silent=True) or {}
    if not entry.get('tmpId'):
        return jsonify({"success": False, "error": "tmpId is required"}), 400
    return _ok(mutate_entries(
        default_path(), lambda es: prune_entries(upsert_entry(es, entry))))


@pipeline_bp.route('/<tmp_id>', methods=['DELETE'])
def delete_pipeline(tmp_id):
    """删除一条（取消排队 / 清理）。未知 id 也返回 200，便于幂等重试。"""
    return _ok(mutate_entries(
        default_path(), lambda es: prune_entries(remove_entry(es, tmp_id))))
```

- [ ] **Step 4: Run → PASS** (7 tests)
- [ ] **Step 5: Commit** — `git add backend/app/api/pipeline.py backend/tests/test_pipeline_api.py && git commit -m "feat: /api/pipeline blueprint (GET/POST/DELETE, prune persisted)"`

---

## Task 3: register the blueprint (the only upstream-file edit)

**Files:** Modify `backend/app/__init__.py`

- [ ] **Step 1:** After the existing status-blueprint block (~line 84), add exactly:

```python
    # 流水线状态（队列 + 卡片状态，服务器持久化）——fork 专有，独立蓝图
    from .api.pipeline import pipeline_bp
    app.register_blueprint(pipeline_bp, url_prefix='/api/pipeline')
```

- [ ] **Step 2:** Boot — `cd backend && ./.venv/Scripts/python.exe -c "from app import create_app; create_app(); print('OK')"`
- [ ] **Step 3:** Full suite — `./.venv/Scripts/python.exe -m pytest tests/ -q` → **268 passed** (252 baseline + 16 new)
- [ ] **Step 4: Commit** — `git commit -am "feat: register pipeline_bp"`

*(B8 needs no new test: `backend/tests/test_auth.py` already proves the gate 401s a generic `/api/...` route, so `/api/pipeline` inherits it.)*

---

## Task 4: frontend api client

**Files:** Create `frontend/src/api/pipeline.js`

- [ ] **Step 1:** Mirror `api/settings.js` (do NOT touch the upstream-owned `api/index.js`):

```javascript
import service from './index'

/** 读取服务器端流水线条目 */
export const getPipeline = () => service.get('/api/pipeline')

/** 新增/更新一条条目（按 tmpId 覆盖） */
export const putPipelineEntry = (entry) => service.post('/api/pipeline', entry)

/** 删除一条条目（幂等） */
export const deletePipelineEntry = (tmpId) => service.delete(`/api/pipeline/${tmpId}`)
```

- [ ] **Step 2:** `cd frontend && npm run build` — clean.
- [ ] **Step 3: Commit** — `git add frontend/src/api/pipeline.js && git commit -m "feat: pipeline api client"`

---

## Task 5: pure `mergeServerEntries` (TDD — the heart of the sync)

**Files:** Modify `frontend/src/store/pipelineQueue.js`, create `frontend/tests/pipelineSync.test.mjs`

**Decision 1 (fixes review issue 1): tombstones live INSIDE the queue object** — `makeQueue()` returns `{entries: [], tombstones: []}`, so `mutate(q => mergeServerEntries(q, serverEntries))` writes both back in one shot and `serialize`/`deserialize` persist both. `mergeServerEntries(q, serverEntries)` reads `q.tombstones` (no third argument).

**Decision 1b (CRITICAL — every reducer must preserve `tombstones`).** All existing pure reducers build a fresh `{entries: ...}` and would silently discard `tombstones`: `enqueue`, `advanceStatus`, `backfillSimId`, `advanceBySimId`, `patchEntry`, `remove`, `reconcileManual`, `pruneFinished`. **Each must return `{...q, entries: ...}`**, and any read of tombstones must guard `(q.tombstones || [])` because existing tests pass bare `{entries:[...]}` literals. Also: the module-load line `q: pruneFinished(deserialize(...))` must preserve tombstones, or a page load wipes them. Without this, one unrelated `setStatus` erases a pending tombstone → the DELETE is never retried → the entry re-hydrates forever (review issue 1's exact symptom, one layer lower).

**Decision 2 (fixes review issue 5 — replaces the rejected heartbeat scheme): display-only entries do NOT consume the slot.** A hydrated entry this browser lacks bytes for is `_displayOnly`: never driven (both advance sites) and **excluded from `activeEntry`/`activeCount`/`headToPromote`**, so it can never deadlock this browser's queue.
**Why that is safe:** the backend already enforces slot=1 + queue=2 for OASIS runs (`services/simulation_queue.py`) — the heavy path is serialised server-side no matter what browsers do. The frontend slot only paces the lighter pre-run stages. A heartbeat + staleness-reclaim scheme was designed and **rejected**: it let a slow tick starve the heartbeat so another tab deleted a *live* job, and it is unnecessary given the server-side queue.

- [ ] **Step 1: Write failing tests** (`frontend/tests/pipelineSync.test.mjs`)

```javascript
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  mergeServerEntries, toServerEntry, advanceStatus, serialize, deserialize,
} from '../src/store/pipelineQueue.js'

const T0 = 1_000_000
const local = (over = {}) => ({
  _tmpId: 't1', status: 'building', prompt: 'p', fileName: 'f.docx',
  fileB64: 'AQID', fileType: '', graphId: null, realSimId: null,
  _dirty: false, _rev: 0, _seenOnServer: false, ...over,
})
const srv = (over = {}) => ({
  tmpId: 't1', status: 'running', prompt: 'p', fileName: 'f.docx',
  graphId: 'g1', simId: 'sim_1', updatedAt: new Date(T0).toISOString(), ...over,
})
const q = (entries = [], tombstones = []) => ({ entries, tombstones })

test('B9: union keeps an in-flight local entry the server has not seen', () => {
  const out = mergeServerEntries(q([local()]), [], T0)
  assert.equal(out.entries.length, 1)
})

test('B10: dirty local wins whole (no status/graphId rollback)', () => {
  const l = local({ status: 'creating', graphId: 'g1', _dirty: true })
  const out = mergeServerEntries(q([l]), [srv({ status: 'building', graphId: null })], T0)
  assert.equal(out.entries[0].status, 'creating')
  assert.equal(out.entries[0].graphId, 'g1')          // not lost -> no rebuild
})

test('B11: field-union preserves local-only fields (file bytes)', () => {
  const out = mergeServerEntries(q([local()]), [srv()], T0)
  assert.equal(out.entries[0].fileB64, 'AQID')        // server never stores this
  assert.equal(out.entries[0].status, 'running')      // server wins on its fields
  assert.equal(out.entries[0].realSimId, 'sim_1')     // simId -> realSimId
})

test('server-only entry hydrates as display-only', () => {
  const out = mergeServerEntries(q([]), [srv({ tmpId: 't9' })], T0)
  assert.equal(out.entries[0]._tmpId, 't9')
  assert.equal(out.entries[0]._displayOnly, true)     // no bytes here
})

test('B4: removal only after seen-then-missing', () => {
  assert.equal(mergeServerEntries(q([local()]), [], T0).entries.length, 1)
  const seen = mergeServerEntries(q([local({ _seenOnServer: true })]), [], T0)
  assert.equal(seen.entries.length, 0)
})

test('B13: tombstone suppresses a stale server entry', () => {
  const out = mergeServerEntries(q([], [{ tmpId: 't1', _deleted: true, _ackedAt: null }]), [srv()], T0)
  assert.equal(out.entries.length, 0)
})

test('B14: tombstone clears only after a DELETE ack, in order', () => {
  const tomb = { tmpId: 't1', _deleted: true, _ackedAt: null }
  assert.equal(mergeServerEntries(q([], [tomb]), [], T0).tombstones.length, 1)   // before ack
  const acked = { ...tomb, _ackedAt: T0 }
  assert.equal(mergeServerEntries(q([], [acked]), [], T0 + 1).tombstones.length, 0)  // after
})

test('B15: dirty outranks seen-then-missing', () => {
  const l = local({ _dirty: true, _seenOnServer: true })
  assert.equal(mergeServerEntries(q([l]), [], T0).entries.length, 1)
})

test('tombstone survives an unrelated mutation and a persist round-trip', () => {
  // Decision 1b: reducers must spread ...q, else this tombstone vanishes
  const withTomb = q([local({ _tmpId: 'other' })], [{ tmpId: 't1', _deleted: true, _ackedAt: null }])
  const after = advanceStatus(withTomb, 'other', 'creating')
  assert.equal((after.tombstones || []).length, 1)
  assert.equal(deserialize(serialize(after)).tombstones.length, 1)
})

test('toServerEntry maps names and omits file bytes', () => {
  const s = toServerEntry(local({ realSimId: 'sim_1' }))
  assert.equal(s.tmpId, 't1'); assert.equal(s.simId, 'sim_1')
  assert.equal(s.fileB64, undefined); assert.equal(s.fileType, undefined)
})
```

- [ ] **Step 2: Run → FAIL** — `cd frontend && node --test tests/pipelineSync.test.mjs`

- [ ] **Step 3: Implement in `pipelineQueue.js`** — change `makeQueue()` to `{entries: [], tombstones: []}`, then add (still **no** api import at top level):

```javascript
// ---- server sync (pure; the driver injects the api) ----
export function toServerEntry(e) {
  return {
    tmpId: e._tmpId, mode: e.mode, status: e.status,
    simId: e.realSimId || null, projectId: e.projectId || null,
    graphId: e.graphId || null, buildTaskId: e.buildTaskId || null,
    prompt: e.prompt, fileName: e.fileName, createdAt: e.createdAt,
  }
}

const SERVER_OWNED = ['status', 'projectId', 'graphId', 'buildTaskId', 'mode', 'prompt', 'fileName', 'createdAt']

function fromServerEntry(s) {
  return {
    _tmpId: s.tmpId, mode: s.mode, status: s.status,
    realSimId: s.simId || null, projectId: s.projectId || null,
    graphId: s.graphId || null, buildTaskId: s.buildTaskId || null,
    prompt: s.prompt, fileName: s.fileName, createdAt: s.createdAt,
    updatedAt: s.updatedAt, _seenOnServer: true, _dirty: false, _rev: 0,
  }
}

// 合并规则见 spec §Frontend sync layer（1..6）
export function mergeServerEntries(q, serverEntries) {
  const serverList = Array.isArray(serverEntries) ? serverEntries : []
  const byId = new Map(serverList.map(s => [s.tmpId, s]))
  const tombs = Array.isArray(q.tombstones) ? q.tombstones : []
  const tombById = new Map(tombs.map(t => [t.tmpId, t]))
  const out = []

  for (const l of q.entries) {
    if (tombById.has(l._tmpId)) continue                 // rule 5
    const s = byId.get(l._tmpId)
    if (!s) {
      if (l._seenOnServer && !l._dirty) continue         // rule 4 (dirty wins: rule 6)
      out.push(l); continue
    }
    if (l._dirty) { out.push({ ...l, _seenOnServer: true }); continue }   // rule 2
    const mapped = fromServerEntry(s)                    // rule 3: field-union
    const merged = { ...l }
    for (const k of SERVER_OWNED) {
      if (mapped[k] !== undefined && mapped[k] !== null) merged[k] = mapped[k]
    }
    if (mapped.realSimId) merged.realSimId = mapped.realSimId
    merged.updatedAt = s.updatedAt
    merged._seenOnServer = true
    out.push(merged)
  }

  const localIds = new Set(q.entries.map(e => e._tmpId))
  for (const s of serverList) {                          // rule 1: hydrate
    if (localIds.has(s.tmpId) || tombById.has(s.tmpId)) continue
    // no file bytes here -> display-only: never driven, never holds the slot
    out.push({ ...fromServerEntry(s), _displayOnly: true })
  }

  // tombstone clears only after a DELETE ack AND a later response lacking the id
  const kept = tombs.filter(t => !(t._ackedAt && !byId.has(t.tmpId)))
  return { ...q, entries: out, tombstones: kept }
}
```

- [ ] **Step 4: Run → PASS** (10 tests)
- [ ] **Step 5:** `node --test tests/*.mjs` — the existing 40 still pass (`makeQueue` shape change must not break them).
- [ ] **Step 6: Commit** — `git add frontend/src/store/pipelineQueue.js frontend/tests/pipelineSync.test.mjs && git commit -m "feat: pure mergeServerEntries (union, dirty-wins, field-union, tombstones)"`

---

## Task 6: store bookkeeping — dirty/_rev, tombstones, persistence (TDD)

**Files:** Modify `frontend/src/store/pipelineQueue.js`, create `frontend/tests/pipelineStore.test.mjs`

*(Review issue 6: the store IS importable under `node --test` — `persist()` no-ops when `localStorage` is undefined, and `entries`/`active` are `computed` so tests read `.value`. So this task gets real tests.)*

- [ ] **Step 1: Write failing tests**

```javascript
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { pipelineStore } from '../src/store/pipelineQueue.js'

function reset() { pipelineStore.reset() }          // new helper for test isolation

test('add seeds _rev and marks dirty', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', prompt: 'p', fileName: 'f', fileB64: 'AQID' })
  const e = pipelineStore.entries.value[0]
  assert.equal(e._rev, 0)
  assert.equal(e._dirty, true)
  assert.deepEqual(pipelineStore.dirtyEntries().map(x => x._tmpId), ['a'])
})

test('markClean clears dirty only if _rev is unchanged', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', prompt: 'p' })
  const rev = pipelineStore.entries.value[0]._rev
  pipelineStore.setStatus('a', 'building')            // bumps _rev
  pipelineStore.markClean('a', rev)                   // stale ack -> ignored
  assert.equal(pipelineStore.entries.value[0]._dirty, true)
  pipelineStore.markClean('a', pipelineStore.entries.value[0]._rev)
  assert.equal(pipelineStore.entries.value[0]._dirty, false)
})

test('cancel removes locally and leaves a tombstone', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', prompt: 'p' })
  pipelineStore.cancel('a')
  assert.equal(pipelineStore.entries.value.length, 0)
  assert.deepEqual(pipelineStore.pendingTombstones().map(t => t.tmpId), ['a'])
})

test('prune tombstones what it drops (so the server converges)', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', prompt: 'p' })
  pipelineStore.setStatus('a', 'done')
  pipelineStore.prune()
  assert.equal(pipelineStore.entries.value.length, 0)
  assert.deepEqual(pipelineStore.pendingTombstones().map(t => t.tmpId), ['a'])
})

test('applyServerMerge writes back entries AND tombstones', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', prompt: 'p' })
  pipelineStore.cancel('a')                           // tombstone for 'a'
  pipelineStore.applyServerMerge([{ tmpId: 'a', status: 'queued', updatedAt: new Date().toISOString() }])
  assert.equal(pipelineStore.entries.value.length, 0)         // suppressed
  assert.equal(pipelineStore.pendingTombstones().length, 1)   // retained for retry
})

test('ackTombstone stamps _ackedAt', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', prompt: 'p' })
  pipelineStore.cancel('a')
  pipelineStore.ackTombstone('a')
  assert.equal(pipelineStore.pendingTombstones().length, 0)   // acked -> not retried
  assert.ok(pipelineStore.tombstones()[0]._ackedAt)           // but still suppressing
})

test('B16: a display-only entry does not hold the slot', () => {
  reset()
  // hydrate an entry this browser has no bytes for
  pipelineStore.applyServerMerge([{ tmpId: 'other', status: 'building', updatedAt: new Date().toISOString() }])
  assert.equal(pipelineStore.entries.value[0]._displayOnly, true)
  assert.equal(pipelineStore.active.value, null)          // does NOT occupy the slot
  pipelineStore.add({ _tmpId: 'mine', prompt: 'p', fileB64: 'AQID' })
  assert.equal(pipelineStore.active.value._tmpId, 'mine') // this browser can still run
})

test('setStatusBySimId marks dirty (manual runs must sync their done)', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', mode: 'manual', prompt: 'p' })
  pipelineStore.setSimId('a', 'sim_1')
  pipelineStore.markClean('a', pipelineStore.entries.value[0]._rev)
  pipelineStore.setStatusBySimId('sim_1', 'done')
  assert.equal(pipelineStore.entries.value[0]._dirty, true)
})
```

- [ ] **Step 2: Run → FAIL** — `node --test tests/pipelineStore.test.mjs`

- [ ] **Step 3: Implement** in `pipelineQueue.js`:
  - `makeQueue()` → `{entries: [], tombstones: []}` (done in Task 5).
  - `serialize`/`deserialize` carry `tombstones` (default `[]`).
  - `mutate(fn, dirtyId)` — apply `fn`; if `dirtyId`, set `_dirty = true` and `_rev = (_rev||0) + 1` on that entry; `persist()`.
  - `add` seeds `_rev: 0, _dirty: true, _seenOnServer: false`.
  - Mark dirty on: `setStatus`, `setSimId`, `patch`, `promoteHead`, `setStatusBySimId`, `reconcileManual` (pass the affected `_tmpId`; for `reconcileManual`/`setStatusBySimId` resolve it from `realSimId`).
  - `cancel(id)` / `remove(id)` → drop the entry **and** push `{tmpId: id, _deleted: true, _ackedAt: null}` to `tombstones`.
  - `prune()` → for every entry it drops, push a tombstone (fixes the ghost loop: a `done` entry must be DELETEd server-side, not just dropped locally).
  - `applyServerMerge(serverEntries)` → `mutate(q => mergeServerEntries(q, serverEntries))` (returns all keys, so the write-back is correct by construction).
  - **Decision 1b:** make every existing reducer return `{...q, entries: ...}` (`enqueue`, `advanceStatus`, `backfillSimId`, `advanceBySimId`, `patchEntry`, `remove`, `reconcileManual`, `pruneFinished`) and guard every tombstone read with `(q.tombstones || [])`. Fix the module-load line so `pruneFinished(deserialize(...))` preserves tombstones.
  - **Decision 2 — display-only never holds the slot:** `activeEntry`, `activeCount`, **`queuedCount`**, and `headToPromote` must ignore entries with `_displayOnly === true`. `queuedCount` matters too: `isFull`/`capacityFull` gate the submit button (`Home.vue`), so another browser's hydrated queued entries would otherwise block THIS browser from submitting.
  - `dirtyEntries()` → entries with `_dirty`.
  - `tombstones()` → all tombstones (suppression list, used by tests/merge).
  - `pendingTombstones()` → tombstones **whose `_ackedAt` is null** (an acked one is awaiting merge-clear; re-DELETEing it every 3s forever would be a leak).
  - `markClean(tmpId, rev)` → clear `_dirty` only if `_rev` is unchanged.
  - `ackTombstone(tmpId)` → set `_ackedAt = Date.now()`.
  - `reset()` (test-only) → `_state.q = makeQueue(); persist()`.

- [ ] **Step 4: Run → PASS**; `node --test tests/*.mjs` — all pass.
- [ ] **Step 5:** `npm run build` clean.
- [ ] **Step 6: Commit** — `git commit -am "feat: store dirty/_rev + tombstones + persisted merge write-back"`

---

## Task 7: driver tick does the sync (ordering + re-entrancy matter)

**Files:** Modify `frontend/src/services/pipelineDriver.js`

- [ ] **Step 1: Imports.** In `startDriver()`, destructure **both** names (review issue 2 — a bare `toServerEntry` would `ReferenceError` inside the `catch` and silently no-op every POST):

```js
  const { pipelineStore, toServerEntry } = await import('../store/pipelineQueue.js')
  const pipeApi = await import('../api/pipeline.js')
```

- [ ] **Step 2: Initial hydration** before the interval:

```js
  try {
    const r = await pipeApi.getPipeline()
    pipelineStore.applyServerMerge(((r.data || r).entries) || [])
  } catch { /* offline: keep local */ }
```

- [ ] **Step 3: Re-entrancy guard** (review issue 3 — the tick now awaits a GET + N POSTs + M DELETEs; at 3s it can overlap itself, causing duplicate writes and stale merges landing after newer local mutations):

```js
  let _tickBusy = false
  setInterval(async () => {
    if (_tickBusy) return
    _tickBusy = true
    try { /* ...tick body... */ } finally { _tickBusy = false }
  }, 3000)
```

- [ ] **Step 4: Tick body order** (review issue 4 — the dirty-POST must come **after** `reconcileManual`/`prune`, or a manual run's `done` is pruned locally before it is ever pushed, and the server re-hydrates it forever):

```js
      // 1. pull server truth
      try {
        const r = await pipeApi.getPipeline()
        store.applyServerMerge(((r.data || r).entries) || [])
      } catch { /* offline */ }

      // 2. existing reconcile (manual runs finish here) + prune (tombstones them)
      try {
        const st = (await api.getSystemStatus()).data || {}
        store.reconcileManual(st.running_simulations || [])
      } catch { /* ignore */ }
      store.prune()

      // 3. push dirty entries (AFTER reconcile so a manual run's 'done' ships)
      for (const e of store.dirtyEntries()) {
        const rev = e._rev
        try { await pipeApi.putPipelineEntry(toServerEntry(e)); store.markClean(e._tmpId, rev) }
        catch { /* retry next tick */ }
      }

      // 4. retry outstanding deletes (tombstones)
      for (const t of store.pendingTombstones()) {
        try { await pipeApi.deletePipelineEntry(t.tmpId); store.ackTombstone(t.tmpId) }
        catch { /* retry next tick */ }
      }

```

**`syncTick` covers steps 1–4 ONLY.** The advance logic (runOne / promoteHead) stays in the interval callback, after `await syncTick(...)` — this is what keeps `runOne` un-awaited (Step 6) and keeps the tick fakes free of `promoteHead`/`_inFlight`.

- [ ] **Step 5: Skip display-only at BOTH advance sites.** The advance logic has two `runOne` call sites — the active entry (`pipelineDriver.js:124`) and the promote branch (`:127`, `promoteHead()`). Guard **both** with `!entry._displayOnly`: this browser has no bytes, so `buildFormData` would throw, `runOne`'s catch would set `failed`, that would push to the server, and the owning browser would lose a live job. (Display-only entries also do not hold the slot — Task 6, Decision 2.)
- [ ] **Step 6: CONSTRAINT — `runOne` must stay un-awaited** inside the tick (it is fire-and-forget today at `pipelineDriver.js:124`). Awaiting it would hold `_tickBusy` for the entire pipeline (minutes), starving the sync steps above. Do not change this.
- [ ] **Step 7: Extract the tick body as `export async function syncTick(deps)`** (deps = `{store, pipeApi, api, toServerEntry}`) so it is testable with injected fakes, mirroring how `runOne` is already dependency-injected. Add `frontend/tests/pipelineTick.test.mjs`:

```javascript
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { syncTick } from '../src/services/pipelineDriver.js'

const fakeStore = (over = {}) => ({
  calls: [],
  applyServerMerge(e) { this.calls.push(['merge', e]) },
  reconcileManual() { this.calls.push(['reconcile']) },
  prune() { this.calls.push(['prune']) },
  dirtyEntries() { return over.dirty || [] },
  pendingTombstones() { return over.tombs || [] },
  markClean(id) { this.calls.push(['clean', id]) },
  ackTombstone(id) { this.calls.push(['ack', id]) },
  ...over,
})

test('tick order: merge -> reconcile -> prune -> push dirty', async () => {
  const store = fakeStore({ dirty: [{ _tmpId: 'a', _rev: 1 }] })
  const pipeApi = { getPipeline: async () => ({ data: { entries: [] } }),
                    putPipelineEntry: async () => { store.calls.push(['put']) },
                    deletePipelineEntry: async () => {} }
  await syncTick({ store, pipeApi, api: { getSystemStatus: async () => ({ data: {} }) },
                   toServerEntry: (e) => e })
  const seq = store.calls.map(c => c[0])
  assert.deepEqual(seq.slice(0, 3), ['merge', 'reconcile', 'prune'])
  assert.ok(seq.indexOf('put') > seq.indexOf('prune'))   // dirty push AFTER prune
})

test('tombstone DELETE is retried and acked', async () => {
  const store = fakeStore({ tombs: [{ tmpId: 'x', _ackedAt: null }] })
  const pipeApi = { getPipeline: async () => ({ data: { entries: [] } }),
                    putPipelineEntry: async () => {},
                    deletePipelineEntry: async () => {} }
  await syncTick({ store, pipeApi, api: { getSystemStatus: async () => ({ data: {} }) },
                   toServerEntry: (e) => e })
  assert.ok(store.calls.some(c => c[0] === 'ack' && c[1] === 'x'))
})

test('a failed GET does not abort the rest of the tick', async () => {
  const store = fakeStore({ dirty: [{ _tmpId: 'a', _rev: 1 }] })
  const pipeApi = { getPipeline: async () => { throw new Error('offline') },
                    putPipelineEntry: async () => { store.calls.push(['put']) },
                    deletePipelineEntry: async () => {} }
  await syncTick({ store, pipeApi, api: { getSystemStatus: async () => ({ data: {} }) },
                   toServerEntry: (e) => e })
  assert.ok(store.calls.some(c => c[0] === 'put'))       // still pushed
})
```

- [ ] **Step 8:** `node --test tests/*.mjs` (existing driver tests must still pass — `runOne` untouched); `npm run build` clean.
- [ ] **Step 9: Commit** — `git commit -am "feat: driver syncs pipeline state each tick (guarded, ordered, tested)"`

---

## Task 8: verify + one deploy

- [ ] **Step 1:** `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q` (≥268 pass) ; `cd frontend && node --test tests/*.mjs` (all pass) ; `npm run build` clean.
- [ ] **Step 2: Upstream-budget check** — diff against **the branch base SHA from Task 0** (NOT `origin/main`, which shows pre-existing fork divergence and can never be empty):
  `git diff --stat <base-sha>..HEAD -- backend/app/services backend/app/api/simulation.py backend/app/api/graph.py backend/app/api/report.py` → **expect empty output.**
- [ ] **Step 3:** Merge branch → main.
- [ ] **Step 4:** Confirm the Space is idle (`/api/status` `busy:false`); then **one** deploy `bash scripts/deploy_hf.sh` (backs up first, aborts if it can't).
- [ ] **Step 5: Live verify**
  - **B1:** enqueue → hard refresh → card still there; `GET /api/pipeline` returns it.
  - **B13:** 取消排队 → card gone and stays gone across two ticks.
  - **B2:** after the deploy, a pre-existing entry is still present (backup/restore carried `pipeline_state.json`).
  - **B6:** open a second tab → it shows the same entries.
- [ ] **Step 6:** Delete the branch.

---

## Notes
- **Never** edit `simulation_runner.py` / `simulation.py` / `graph.py` / `report.py` here — the point is upstream-merge cost.
- `pipelineQueue.js` must stay importable under `node --test` → **no** top-level api import.
- File bytes never go to the server (50MB upload cap); a browser without them shows the card (`_displayOnly`) but never drives it and never holds the slot. The backend's own slot=1/queue=2 (`services/simulation_queue.py`) is what serialises the heavy OASIS runs.
- Known, accepted: hydration bypasses `enqueue`'s capacity check, so two tabs can briefly exceed 3 entries; the extras are display-only: they never advance and never hold the slot.
