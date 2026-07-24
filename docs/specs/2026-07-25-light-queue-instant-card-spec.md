# Light Queue + Instant Card + 运行中 Badge — Spec

**Date:** 2026-07-25
**Status:** Design approved (light, frontend-first). Awaiting spec sign-off.
**Approach:** No server rebuild. Optimistic UI + one app-level auto-pilot
driver + frontend gating. Backend untouched for orchestration; the
existing `/api/status` queue fields are read for status visibility.

## Why light (not the server rebuild)

The heavy server-orchestration (extract services, placeholder DB
records, multipart submit, queue refactor) was over-engineered. The
real needs are three:

1. Instant feedback card the moment you click start.
2. Visible 运行中 / 排队中 state on history cards.
3. Can't accidentally run 3 projects at once (the OOM/orphan cause,
   confirmed from Space logs: 3 graph builds, only 1 survived).

All three are achievable in the frontend by showing an optimistic
in-progress card and mocking the in-progress UI until the server
catches up, then wiring to real `/api/status` data.

## Decisions locked (by user)

- Slot = 1 active pipeline; Queue = 2 waiting (total 3).
- **Option (b):** queued projects **auto-start** when the active one
  finishes — via one always-on driver in the app. Survives in-app
  navigation; requires the tab to stay open (accepted).
- Instant card on **both** auto-pilot and manual click.
- **Auto-pilot stays on Home** after submit; **manual navigates into
  the step flow** as today.
- 运行中 badge added (mirrors the shipped 排队中 badge).

## Behaviors (testable — entry / action / result)

### B-run — 运行中 badge
- Entry: a simulation is running.
- Result: its history card shows a green **运行中** corner badge, driven
  by `id ∈ /api/status.running_simulations`. Mirrors the 排队中 badge.

### B-instant — instant card on click (auto AND manual)
- Entry: Home, file + prompt ready.
- Action: click 启动引擎 (manual) or 自动直达报告 (auto).
- Result: a card appears in the history list **immediately**, labelled
  **生成中**, before graph build finishes. Clickable → opens that
  project's live view. Held as an optimistic entry in an in-memory app
  store that survives SPA navigation within the open tab.

### B-mock-to-real — 生成中 → 运行中 → 完成
- The optimistic card shows 生成中 through graph-build/prepare.
- Once the real simulation id appears in
  `/api/status.running_simulations`, the card flips to the real 运行中
  badge and merges with the real history record (matched by sim id).
  The mock is replaced, never duplicated.

### B-queue — line up while one is active (option b)
- Entry: one pipeline active (生成中 or 运行中), queue has < 2 entries.
- Action: click start for another project.
- Result: the new project becomes an optimistic **排队中** card
  (等待中 + 取消排队). It does NOT begin graph build. The app-level
  driver starts it automatically when the active pipeline finishes.

### B-full — capacity full disables start
- Entry: 1 active + 2 queued (3 total).
- Result: start section (both buttons) disabled + `队列已满` hint.
  (Already built; reused.)

### B-cancel — 取消排队
- Entry: an optimistic 排队中 card.
- Action: click 取消排队.
- Result: removed from the queue before it starts; frees a slot;
  re-enables the start section. (Badge/button already built.)

### B-promote — auto-start next on completion (option b, the driver)
- Entry: active pipeline reaches terminal (report done / failed).
- Result: the driver dequeues the oldest 排队中 project and begins its
  pipeline automatically — no manual click, works while you sit on Home.

## App-level auto-pilot driver (the core light piece)

Move auto-pilot orchestration OUT of the per-Step pages into one
composable mounted once at `App.vue`, so it keeps advancing regardless
of the current route.

- **Pending store** (in-memory reactive; e.g. a small module store):
  ordered list of submissions, each `{ id, file, prompt, status }`,
  status ∈ `queued | ontology | building | creating | preparing |
  running | done | failed`. Holds the `File` object in memory (survives SPA
  navigation; lost only on full page reload — accepted).
- **Driver loop:** for the single head-of-queue active submission,
  advance through the EXISTING endpoints in sequence (graph build →
  create → prepare → start), polling task status between steps — the
  same calls the Step pages make today, hoisted to app level.
- **One active at a time:** the driver only advances the head; the rest
  stay `queued`. This is what makes 3-concurrent impossible — the real
  fix.
- Manual per-Step flow stays for click-through users; a manual start
  also registers in the store so it counts toward the slot.

## Gating (frontend)

- Start section disabled when the store holds 1 active + 2 queued, with
  `/api/status.capacity_full` as a secondary guard.
- Auto-pilot submit stays on Home; manual navigates into the steps.

## Backend

- Untouched for orchestration. `/api/status` already returns
  `running_simulations`, `queued_simulations`, `capacity_full`; the
  frontend reads these to flip mock→real and to gate. The shipped
  run-queue stays as a harmless server-side backstop.

## Reconciliation & ownership (resolves review blockers)

These pin the exact rules an implementer would otherwise guess.

### R1 — Temp id + card keying
Each submission gets a unique client temp id `tmp_<n>` at click. History
card `:key` becomes `project.simulation_id || project._tmpId`. Pre-create
optimistic cards key on their temp id (no more `undefined` collisions).

### R2 — realSimId backfill + dedup (mock→real)
The driver made the `create` call, so it learns the real `simulation_id`.
It writes `realSimId` back onto the store entry. `HistoryDatabase`
renders a **computed merge**: `serverList` ++ pending entries whose
`realSimId` is NOT already present in `serverList`. Once a server record
with that `realSimId` appears, the pending (optimistic) entry is dropped
— never both. The `完成/done` server record wins.

### R3 — history re-fetch trigger
`loadHistory()` currently runs only on mount/activate/route-change. Add a
trigger: the driver signals each stage transition (and on `create` /
terminal), and `HistoryDatabase` re-fetches history on that signal (plus
a low-frequency safety poll). This is what makes the mock→real swap fire
while the user sits on Home.

### R4 — card status source precedence
A card's queued/running/生成中 state = **store status first**, then
`/api/status` id. Pre-`/start` cards (no sim id yet) get their 生成中 /
排队中 from the store. Once `realSimId ∈ /api/status.running_simulations`,
the real 运行中 badge takes over. One resolver, no disagreement.

### R5 — single promoter (the double-start / OOM fix)
The **frontend driver is the sole concurrency controller**, and the
**in-memory store is the synchronous slot gate** (not `/api/status`,
which lags). It never fires two `/start` calls concurrently (advances
only the head). Because of that, the backend run-queue's
`submit_start`/`promote_next` **never engage** (every `/start` the
driver makes sees zero running → starts immediately, never queued) — so
it stays dormant, no second promoter.

The race is closed by **enqueue, not by disabling**: when the store slot
is occupied, a start click (manual or auto) **adds the project to the
queue instead of calling `/start`** — so no second `/start` can race the
driver. The start section is only fully **disabled at capacity** (1
active + 2 queued), per B-full; below capacity it stays clickable so you
can queue (B-queue). A manual click registers in the store at click time
(before `/api/status` reflects it), so the gate is synchronous. Backend
untouched.

### R6 — manual vs auto driver boundary
The driver advances **only auto-pilot submissions**. A manual submission
occupies a slot but is driven by its own Step pages (as today); the
driver skips it and detects its completion via `/api/status` before
promoting the next queued item. No project is ever driven by both.

### R8 — hard-refresh survival (persistent, isolated, tiny)
The pending store persists to **localStorage** so instant cards + the
queue survive a full page reload / tab reopen — not just SPA navigation.
- Each entry serialized as `{ id, prompt, status, realSimId, fileB64,
  fileName, fileType }`. The `File` is stored base64 (uploaded docx are
  ~35KB → ~47KB base64; 3 queued ≈ 140KB, far under the ~5MB cap).
- On app load, the store **rehydrates** from localStorage (base64 →
  File) and the app-level driver **resumes** the active/queued entries
  from their last `status`.
- Fully frontend, isolated to the store module + one localStorage key.
  **No server-side logic touched.** Entries are pruned from localStorage
  once `done` / reconciled to a real server record.

### R7 — pre-create card click target + ontology stage
Store status enum includes the distinct `ontology` stage (step 1) before
`building`. Clicking a 生成中 card **before** it has a `simulation_id`
routes to the active live view if one exists, else is a no-op (not a
broken route); once `realSimId` exists, it deep-links to that project.

## Out of scope

- Backend pipeline orchestrator, placeholder DB records, multipart
  submit endpoint — dropped as over-engineering. Backend core logic
  untouched.
- Queue reordering (FIFO only).
- (Hard-refresh survival IS now in scope — see R8, localStorage-persisted.)

## Test matrix (TDD)

- **Pending store (pure JS unit):** enqueue / dequeue / cancel / FIFO /
  capacity_full / status transitions — mirrors the backend queue tests.
- **Driver step-sequence (mocked API):** advances build→create→prepare
  →start in order; on terminal, promotes next; stops at head only.
- **Card-state derivation:** 生成中 / 运行中 / 排队中 from store + status.
- **Live verification:** 运行中 badge on the running sim; instant card
  on click; 2nd click → 排队中; auto-start on completion.
