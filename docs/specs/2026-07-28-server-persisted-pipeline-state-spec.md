# Server-Persisted Pipeline State — Spec

**Date:** 2026-07-28
**Status:** Design approved; spec revised after review. Awaiting sign-off.
**Constraint (decisive):** this is a **fork** that rebases against a
frequently-updating upstream. The design MUST minimise edits to
upstream-owned files.

## Problem

The queue and the pre-run card states (生成中 / 排队中) live **only in the
browser** (localStorage pipeline store). Observed in production:

- The queue disappears (localStorage churn, deploys, another tab).
- Cards cannot reflect backend truth — the backend has no knowledge of
  生成中 / 排队中 entries, so nothing can reconcile them.
- Ghost/stale cards after a restart killed an in-flight pipeline.

Root cause: **pipeline state has no server-side home.**

## Upstream-impact constraint (why not a backend rebuild)

Measured divergence from `origin/main`:

- **Already-diverged upstream files** (cost on every sync):
  `api/simulation.py` +189, `services/simulation_runner.py` +154,
  `api/report.py` +48, `api/graph.py` +17, `config.py`, `utils/llm_client.py`,
  the two generators, `scripts/run_*.py`.
- **New isolated files** (~zero sync cost): 25+ files upstream never
  touches.
- **Both frontend pipeline files are fork-only** — `frontend/src/store/
  pipelineQueue.js` and `frontend/src/services/pipelineDriver.js` do not
  exist upstream (`git cat-file -e origin/main:<path>` fails), so the
  entire frontend change carries **zero** merge cost.

Therefore: new logic in NEW files; upstream-owned files get at most a
blueprint registration. A server-orchestrated pipeline rebuild (deep
edits to `simulation_runner`) is **rejected** — permanent merge pain in
the hottest files.

## Verified facts (checked against code)

- **Auth is app-level.** `auth.py` registers a `before_request` gate that
  401s any `/api/*` path not in the exempt list (`/api/auth/`, `/static/`,
  `/assets/`, `/health`). A new blueprint under `/api` therefore inherits
  the access-code gate automatically. Covering test: `tests/test_auth.py`
  (asserts 401 on an arbitrary `/api/...` route). Note the
  `test_settings_api.py` fixture builds a bare Flask app **without**
  `init_auth`, so B8 is covered by `test_auth.py`, not by mirroring that
  fixture.
- **Backup covers the whole data dir.** `backup.py` does
  `tar.add(data_dir, arcname=".")` over `Config.UPLOAD_FOLDER`, so a new
  `uploads/pipeline_state.json` is backed up + restored by the existing
  deploy flow exactly like `app_settings.json`.
- **Blueprint registration is 2 lines** (import + `register_blueprint`) in
  `app/__init__.py`, which is already fork-diverged (+29/−2, four
  fork-added blueprint blocks). Marginal cost ≈ zero.

## Design

### New file 1 — `backend/app/utils/pipeline_state.py`

JSON store in the data dir (covered by backup), mirroring the working
`app_settings.py` pattern (fresh read per call, tolerant of a missing or
corrupt file).

**Server-stored entry shape** (deliberately excludes file bytes):
```
{tmpId, mode, status, simId, projectId, graphId, buildTaskId,
 prompt, fileName, createdAt, updatedAt}
```
**NOT stored server-side:** `fileB64`, `fileType`, the live `File` — too
large (uploads cap 50MB) and browser-local by nature. They remain in
localStorage only.

Pure, unit-testable functions (no Flask, no I/O in the pure ones):
- `load_entries(path)` → list; missing/corrupt → `[]`
- `upsert_entry(entries, entry, now)` → new list; match on `tmpId`,
  replace-or-append, stamp `updatedAt`
- `remove_entry(entries, tmp_id)` → new list
- `prune_entries(entries, now, ttl_hours=24)` → drops `done`/`failed`
  and anything whose `updatedAt` is older than the TTL
- `save_entries(path, entries)` — temp-file + `os.replace` (atomic
  replacement; keeps a torn write from ever producing a corrupt file)

**Locked read-modify-write (the lost-update fix).** A lock inside
`save_entries` alone does NOT prevent lost updates — two concurrent
requests can both `load` `[A]`, then write `[A,B]` and `[A,C]`, losing
`B`. So all mutation goes through ONE locked entry point:

```
mutate_entries(path, fn) -> list      # module-level threading.Lock held
    with _LOCK:                       # across load -> fn -> save
        entries = load_entries(path)
        entries = fn(entries)         # a pure function above
        save_entries(path, entries)
        return entries
```
The API handlers call `mutate_entries(path, lambda es: upsert_entry(...))`
etc. — never load/save separately. The pure functions stay pure and
unit-testable; only `mutate_entries` touches the lock. (Server is
single-process `app.run(threaded=True)`, so a module lock is sufficient.)

### New file 2 — `backend/app/api/pipeline.py`

Blueprint `pipeline_bp`, registered with `url_prefix='/api/pipeline'`
(the `settings.py` convention):
- `GET  ''` (`strict_slashes=False`) → `{success, data:{entries:[...]}}`,
  pruned **and the prune persisted** (so the file cannot grow unbounded
  when only GETs happen)
- `POST ''` (`strict_slashes=False`) → body is one entry → upsert →
  returns the pruned list
- `DELETE '/<tmp_id>'` → remove → returns the pruned list

Auth: inherited from the app-level gate (verified above).

### New file 3 — `frontend/src/api/pipeline.js`

`getPipeline()` / `putPipelineEntry(entry)` / `deletePipelineEntry(tmpId)`.
A new sibling of the fork-only `api/settings.js`; `api/index.js` (upstream-
owned) is **not** modified.

### Upstream-file change — 2 lines
`backend/app/__init__.py`: import + register `pipeline_bp`. No other
upstream-owned backend file is touched.

### Frontend sync layer (rewritten after review)

localStorage remains the offline cache **and the only home of the file
bytes**; the server is the source of truth for *status/membership*.

**Field mapping** (store ⇄ server):
| store        | server      |
|--------------|-------------|
| `_tmpId`     | `tmpId`     |
| `realSimId`  | `simId`     |
| `projectId`  | `projectId` |
| `graphId`    | `graphId`   |
| `buildTaskId`| `buildTaskId`|
| `status`, `mode`, `prompt`, `fileName`, `createdAt` | same names |
| `fileB64`, `fileType`, `file` | **not sent** |

**Per-entry dirty tracking.** Every local mutation bumps `_rev` and sets
`_dirty = true`. A successful POST clears `_dirty` **only if `_rev` is
unchanged** since the POST started (else a newer local mutation is still
pending).

**Pure merge function** `mergeServerEntries(local, server)` —
unit-testable, no fetch, no DOM:
1. **Union by `_tmpId`.** Never drop a local entry merely because the
   server has not seen it yet (fixes: in-flight submission vanishing).
2. **Dirty local wins whole.** If a local entry is `_dirty`, the server
   copy is ignored for that entry this round (fixes: driver status
   rollback re-firing `buildGraph`/`prepare` — the double-fire/OOM class).
3. **Clean local: field-union.** Server is authoritative **only for the
   fields it stores**; local-only fields (`fileB64`, `fileType`, `file`)
   are always preserved (fixes: hydrated entry with no file bytes
   throwing `atob(undefined)` → dead pipeline).
4. **Removal requires evidence.** A local entry is dropped only if it
   previously appeared in a server response and has since disappeared
   (tracked by a `_seenOnServer` flag) — never on first sight of a
   server list.
5. **Delete tombstone (prevents a cancelled entry resurrecting).**
   取消排队/delete removes the entry from the visible list *immediately*
   (keeping today's optimistic UX) and records a **tombstone**
   `{tmpId, _deleted: true}`. While a tombstone exists:
   - the merge **suppresses** that `tmpId` even if a stale `GET` still
     returns it (kills the ~3s flicker and the permanent ghost when a
     DELETE fails), and
   - each driver tick **retries the DELETE** (deletes get the same retry
     treatment as dirty POSTs — not POST-only), and
   - **any in-flight or pending POST for that `tmpId` is dropped** (a
     tombstoned entry must never be re-created by a racing write).

   **Clearing (order matters).** The tombstone is cleared only after a
   **successful DELETE ack**, and only by a response *received after*
   that ack which does not contain the `tmpId`. Clearing on any earlier
   response is unsafe: a DELETE could overtake a still-in-flight POST,
   the reply would lack the id, the tombstone would clear, and the POST
   would then re-create the entry server-side — resurrecting exactly the
   undeletable ghost this rule exists to kill.

   **The tombstone is persisted** to localStorage alongside the entries,
   so a hard refresh inside a failed-DELETE window does not resurrect the
   entry.

   Without this rule, a failed DELETE means the entry is re-hydrated
   forever by union-by-tmpId, holding a queue slot for the whole TTL —
   exactly what B5 forbids.
6. **Precedence when rules collide.** If an entry is both `_dirty` and
   seen-then-missing on the server, **dirty wins** (a local mutation is
   newer evidence than a remote absence). A tombstone (rule 5) is the
   only **locally-initiated** removal path and outranks both. Rule 4's
   seen-then-missing removal remains in force for entries deleted
   **elsewhere** (another tab) — otherwise a cross-tab cancel would leave
   a permanent local ghost.

**Driver skips unrunnable entries.** An entry hydrated from the server in
a browser that lacks its file bytes (localStorage cleared, different
browser) is **display-only**: the driver refuses to advance it (guard:
no `fileB64` and no `projectId` → skip). It still renders, and the TTL
prune eventually clears it. Known, accepted limitation of keeping the
driver browser-side.

**Every membership/status mutation syncs** (exhaustive list — the review
found four missing):
`add`, `setStatus`, `setSimId`, `patch`, `cancel`, `remove`,
`prune`, `setStatusBySimId`, `reconcileManual`, `promoteHead`.
(`setStatusBySimId` + `reconcileManual` are the only paths by which a
**manual** run reaches `done`; leaving them unsynced would resurrect a
生成中 ghost on every refresh for the whole TTL — the exact thing B5
promises to prevent.)

**Module shape — no static api import.** `pipelineQueue.js` must NOT
`import` the api service at top level: `src/api/index.js` is not
importable under `node --test` (proven: directory-import of `src/i18n`
fails), and `frontend/tests/pipelineQueue.test.mjs` imports the store
directly. Use the same shape `pipelineDriver.js` already documents:
dynamic `import()` at call time / dependency injection, with
`mergeServerEntries` exported as a pure function for unit tests.

**Where sync is driven:** the store singleton is built synchronously at
module import, so hydration cannot happen there. `startDriver()` (App.vue,
already mounted once) performs the initial `GET` and, on each existing
3s tick: (a) re-`GET`s + merges, (b) re-POSTs any entry still `_dirty`,
and (c) re-issues DELETE for any outstanding tombstone (rule 5) — deletes
get the same retry treatment as dirty POSTs.

## Behaviors (testable)

- **B1 — persist across refresh.** Enqueue → hard refresh → the entry is
  still present (server `GET` + local bytes) and the card renders, and
  the pipeline can still run.
- **B2 — survives deploy.** The store lives in the data dir → carried by
  the existing backup→restore.
- **B3 — upsert by tmpId.** POSTing the same `tmpId` twice replaces
  (never duplicates) and refreshes `updatedAt`.
- **B4 — delete.** `DELETE /api/pipeline/<tmpId>` removes exactly that entry.
- **B5 — prune, incl. manual runs.** `done`/`failed` and past-TTL entries
  are dropped and the prune is persisted; a manual run that finished
  reaches `done` server-side (via synced `setStatusBySimId`/
  `reconcileManual`) so no ghost survives a refresh.
- **B6 — cross-tab sync.** Two clients see the same entries.
- **B7 — corrupt/missing file tolerated.** → `[]`, never a 500.
- **B8 — auth-gated.** `/api/pipeline` 401s without the access code
  (inherited app-level gate; covered by `test_auth.py`'s generic case).
- **B9 — merge preserves an in-flight local entry.** `mergeServerEntries`
  with a local entry absent from the server list keeps it.
- **B10 — merge does not roll back a dirty entry.** Local `_dirty` entry
  at `creating` + server copy at `building` → result stays `creating`
  (and `graphId` is not lost).
- **B11 — merge preserves local-only fields.** Clean local entry with
  `fileB64` + server copy without it → `fileB64` survives.
- **B12 — concurrent upserts don't lose updates.** Two threads each call
  `mutate_entries(path, upsert(<different tmpId>))` concurrently → the
  final file contains **both** entries (proves the lock spans
  load→modify→save, not just the write).
- **B13 — tombstone suppresses a stale server entry.** Local has a
  tombstone for `t1`; a `GET` still returns `t1` → merge result does NOT
  contain `t1` (no flicker, no permanent ghost when a DELETE fails).
- **B14 — tombstone clears only after a DELETE ack, in order.** A `GET`
  lacking `t1` that arrives *before* the DELETE ack does NOT clear the
  tombstone; only a response received *after* a successful DELETE ack
  and lacking `t1` clears it (so a racing POST can't resurrect the
  entry, and a future entry reusing the id isn't suppressed forever).
- **B15 — dirty outranks seen-then-missing.** Entry is `_dirty` AND was
  seen-then-missing on the server → kept (dirty wins), unless a
  tombstone exists.

## Out of scope

- Moving the driver to the backend (rejected: upstream merge cost).
- Any change to `simulation_runner.py` / `simulation.py` / the existing
  backend run-queue.
- Multi-user isolation (single shared deployment, as today).
- Running an entry in a browser that lacks its file bytes (display-only).

## Test matrix (TDD)

**Backend pure:** load/upsert/remove/prune round-trip; corrupt → `[]`;
TTL + done/failed drop (B3, B5, B7). **Backend concurrency:** two threads
calling `mutate_entries` with different `tmpId`s → both survive (B12).
**Backend API** (Flask test client mirroring `test_settings_api.py`):
GET/POST/DELETE shapes + GET persists prune (B1, B4, B5).
**Frontend pure** (`mergeServerEntries`, no fetch/DOM): union keeps
in-flight local (B9); dirty local wins (B10); field-union preserves
`fileB64` (B11); removal only after seen-then-gone (B4); tombstone
suppresses a stale server entry (B13) and clears on ack (B14); dirty
outranks seen-then-missing (B15).
**Live:** enqueue → refresh → card + pipeline survive (B1); deploy →
card survives (B2).
