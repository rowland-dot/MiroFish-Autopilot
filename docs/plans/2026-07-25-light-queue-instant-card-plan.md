# Light Queue + Instant Card + 运行中 Badge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Instant optimistic history cards on click (both auto + manual), a 运行中 badge, and a real one-at-a-time queue (1 active + 2 waiting) driven entirely in the frontend — surviving navigation and hard refresh — without touching backend core logic.

**Architecture:** A persisted in-memory pipeline store (localStorage-backed, base64 file) holds submissions. One app-level driver, mounted once in `App.vue`, advances the head submission through the existing step endpoints (ontology → build → create → prepare → start), polling between steps, then promotes the next. History cards merge server records with the store's optimistic entries. The store is the synchronous slot gate, so no second `/start` ever races — the backend run-queue stays dormant.

**Tech Stack:** Vue 3 (Composition API, `<script setup>`), Vite, existing axios API modules, `node --test` for pure-JS unit tests. Spec: `docs/specs/2026-07-25-light-queue-instant-card-spec.md`.

---

## File structure

**Create:**
- `frontend/src/store/pipelineQueue.js` — pending-submission store: ordered list, status transitions, capacity, realSimId backfill, dedup helper, localStorage persist + rehydrate (base64 file). Pure logic + a reactive singleton.
- `frontend/src/store/fileCodec.js` — tiny isolated base64 ⇄ File helpers (so the store stays focused).
- `frontend/src/services/pipelineDriver.js` — the app-level driver: advance head through the endpoint sequence, poll, promote next. Auto-pilot submissions only.
- `frontend/tests/pipelineQueue.test.mjs` — pure store unit tests.
- `frontend/tests/fileCodec.test.mjs` — codec round-trip test.
- `frontend/tests/pipelineDriver.test.mjs` — driver sequence with mocked API.

**Modify:**
- `frontend/src/App.vue` — start the driver once (survives all route changes).
- `frontend/src/views/Home.vue` — submit → enqueue (instant card); auto stays on Home, manual navigates into steps; start section disabled at capacity from the store.
- `frontend/src/components/HistoryDatabase.vue` — merge store entries into the list (computed), temp-id keying, 运行中 + 生成中 badges, status resolver, re-fetch on driver signal.

**Do NOT touch:** any `backend/**` orchestration, the step endpoints, or the shipped backend run-queue. This is frontend-only.

---

## Task 1: base64 file codec (tiny, isolated)

**Files:**
- Create: `frontend/src/store/fileCodec.js`
- Test: `frontend/tests/fileCodec.test.mjs`

- [ ] **Step 1: Write the failing test**

```javascript
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { fileToB64, b64ToFile } from '../src/store/fileCodec.js'

test('round-trips a file through base64', async () => {
  const original = new File([new Uint8Array([1, 2, 3, 4])], 'x.docx', { type: 'application/docx' })
  const enc = await fileToB64(original)
  assert.equal(typeof enc.b64, 'string')
  assert.equal(enc.name, 'x.docx')
  assert.equal(enc.type, 'application/docx')
  const back = b64ToFile(enc)
  assert.equal(back.name, 'x.docx')
  assert.equal(back.size, 4)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node --test tests/fileCodec.test.mjs`
Expected: FAIL (module not found). Note: `File`/`Blob`/`FileReader` exist in Node 20+ test env; if `FileReader` is missing, implement `fileToB64` via `Buffer.from(await file.arrayBuffer())`.

- [ ] **Step 3: Write minimal implementation**

```javascript
// Base64 <-> File, isolated so the store stays focused. Browser + Node-safe.
export async function fileToB64(file) {
  const buf = new Uint8Array(await file.arrayBuffer())
  let bin = ''
  for (let i = 0; i < buf.length; i++) bin += String.fromCharCode(buf[i])
  const b64 = (typeof btoa === 'function') ? btoa(bin) : Buffer.from(buf).toString('base64')
  return { b64, name: file.name, type: file.type || '' }
}

export function b64ToFile({ b64, name, type }) {
  const bin = (typeof atob === 'function') ? atob(b64) : Buffer.from(b64, 'base64').toString('binary')
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return new File([bytes], name, { type })
}
```

- [ ] **Step 4: Run test to verify it passes** — Run: `node --test tests/fileCodec.test.mjs` → PASS
- [ ] **Step 5: Commit** — `git add frontend/src/store/fileCodec.js frontend/tests/fileCodec.test.mjs && git commit -m "feat: base64 file codec for pipeline queue persistence"`

---

## Task 2: pipelineQueue store — pure logic (TDD)

Mirrors the backend queue (slot=1, queue=2) but frontend-owned and richer (statuses, temp ids, realSimId backfill, dedup). Build the **pure** functions first; the reactive singleton + localStorage wrap comes in Task 3.

**Files:**
- Create: `frontend/src/store/pipelineQueue.js`
- Test: `frontend/tests/pipelineQueue.test.mjs`

Status enum: `queued | ontology | building | creating | preparing | running | done | failed`.
Active statuses (occupy the slot): everything except `queued`, `done`, `failed`.

- [ ] **Step 1: Write the failing tests**

```javascript
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  makeQueue, enqueue, activeEntry, isFull, capacityFull,
  advanceStatus, backfillSimId, cancel, remove, headToPromote,
  mergeForDisplay, ACTIVE_STATUSES,
} from '../src/store/pipelineQueue.js'

const sub = (id, over = {}) => ({ _tmpId: id, prompt: 'p', fileName: 'x.docx', status: 'queued', realSimId: null, ...over })

test('enqueue respects slot=1 + queue=2 (capacity 3)', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))          // becomes active (slot free)
  assert.equal(q.entries[0].status, 'ontology')     // first active status
  q = enqueue(q, sub('b'))          // queued
  q = enqueue(q, sub('c'))          // queued
  assert.equal(capacityFull(q), true)               // 1 active + 2 queued
  q = enqueue(q, sub('d'))          // rejected
  assert.equal(q.entries.length, 3)
})

test('only one active at a time', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = enqueue(q, sub('b'))
  assert.equal(q.entries.filter(e => ACTIVE_STATUSES.includes(e.status)).length, 1)
  assert.equal(activeEntry(q)._tmpId, 'a')
})

test('advanceStatus moves the active entry forward', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = advanceStatus(q, 'a', 'building')
  assert.equal(q.entries[0].status, 'building')
})

test('backfillSimId writes realSimId on the entry', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = backfillSimId(q, 'a', 'sim_123')
  assert.equal(q.entries[0].realSimId, 'sim_123')
})

test('headToPromote returns oldest queued when no active', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = enqueue(q, sub('b'))
  q = advanceStatus(q, 'a', 'done')     // active finished
  const head = headToPromote(q)
  assert.equal(head._tmpId, 'b')
  assert.equal(headToPromote(makeQueue()), null)
})

test('headToPromote is null while something is active', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = enqueue(q, sub('b'))
  assert.equal(headToPromote(q), null)   // a still active
})

test('cancel / remove drop a queued entry', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = enqueue(q, sub('b'))
  q = cancel(q, 'b')
  assert.deepEqual(q.entries.map(e => e._tmpId), ['a'])
})

test('mergeForDisplay suppresses optimistic entry once server has its realSimId', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = backfillSimId(q, 'a', 'sim_1')
  const serverList = [{ simulation_id: 'sim_1', foo: 1 }]
  const merged = mergeForDisplay(serverList, q)
  // server record wins; optimistic 'a' dropped (no dup)
  assert.equal(merged.length, 1)
  assert.equal(merged[0].simulation_id, 'sim_1')
})

test('mergeForDisplay keeps optimistic entry not yet in server list', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))    // no realSimId yet
  const merged = mergeForDisplay([], q)
  assert.equal(merged.length, 1)
  assert.equal(merged[0]._tmpId, 'a')
  assert.equal(merged[0]._optimistic, true)
})
```

- [ ] **Step 2: Run to verify fail** — `node --test tests/pipelineQueue.test.mjs` → FAIL (module missing)

- [ ] **Step 3: Implement the pure functions**

```javascript
// frontend/src/store/pipelineQueue.js  (pure section)
export const ACTIVE_STATUSES = ['ontology', 'building', 'creating', 'preparing', 'running']
const SLOT_LIMIT = 1
const QUEUE_LIMIT = 2
const FIRST_ACTIVE = 'ontology'

export function makeQueue() { return { entries: [] } }

function activeCount(q) { return q.entries.filter(e => ACTIVE_STATUSES.includes(e.status)).length }
function queuedCount(q) { return q.entries.filter(e => e.status === 'queued').length }

export function activeEntry(q) { return q.entries.find(e => ACTIVE_STATUSES.includes(e.status)) || null }
export function isFull(q) { return activeCount(q) >= SLOT_LIMIT && queuedCount(q) >= QUEUE_LIMIT }
export function capacityFull(q) { return isFull(q) }

export function enqueue(q, entry) {
  if (isFull(q)) return q                          // rejected at capacity
  const startActive = activeCount(q) < SLOT_LIMIT
  const e = { ...entry, status: startActive ? FIRST_ACTIVE : 'queued' }
  return { entries: [...q.entries, e] }
}

export function advanceStatus(q, tmpId, status) {
  return { entries: q.entries.map(e => e._tmpId === tmpId ? { ...e, status } : e) }
}

export function backfillSimId(q, tmpId, realSimId) {
  return { entries: q.entries.map(e => e._tmpId === tmpId ? { ...e, realSimId } : e) }
}

export function cancel(q, tmpId) { return remove(q, tmpId) }
export function remove(q, tmpId) {
  return { entries: q.entries.filter(e => e._tmpId !== tmpId) }
}

export function headToPromote(q) {
  if (activeCount(q) >= SLOT_LIMIT) return null
  return q.entries.find(e => e.status === 'queued') || null
}

// Merge server history with optimistic entries. Server record wins;
// an optimistic entry whose realSimId is already in the server list is dropped.
export function mergeForDisplay(serverList, q) {
  const serverIds = new Set(serverList.map(r => r.simulation_id))
  const optimistic = q.entries
    .filter(e => e.status !== 'done')
    .filter(e => !(e.realSimId && serverIds.has(e.realSimId)))
    .map(e => ({ _optimistic: true, _tmpId: e._tmpId, simulation_id: e.realSimId || null,
                 status: e.status, files: [{ filename: e.fileName }],
                 simulation_requirement: e.prompt, created_at: e.createdAt }))
  return [...optimistic, ...serverList]     // optimistic (newest) on top
}
```

- [ ] **Step 4: Run to verify pass** — `node --test tests/pipelineQueue.test.mjs` → PASS
- [ ] **Step 5: Commit** — `git add frontend/src/store/pipelineQueue.js frontend/tests/pipelineQueue.test.mjs && git commit -m "feat: pipeline queue pure logic (slot=1,queue=2,merge,backfill)"`

---

## Task 3: reactive singleton + localStorage persist/rehydrate (R8)

Wrap the pure functions in a Vue `reactive` singleton and persist to localStorage so cards survive hard refresh.

**Files:**
- Modify: `frontend/src/store/pipelineQueue.js` (append the reactive + persistence layer)
- Test: extend `frontend/tests/pipelineQueue.test.mjs`

- [ ] **Step 1: Failing test for persistence round-trip** (pure, inject a fake storage)

```javascript
test('serialize/deserialize round-trips through a storage-like string', () => {
  let q = makeQueue()
  q = enqueue(q, { _tmpId: 'a', prompt: 'p', fileB64: 'AQID', fileName: 'x.docx', fileType: '', realSimId: null })
  const json = serialize(q)
  const back = deserialize(json)
  assert.equal(back.entries[0]._tmpId, 'a')
  assert.equal(back.entries[0].fileB64, 'AQID')
  assert.equal(back.entries[0].status, 'ontology')
})
```
(import `serialize, deserialize` from the store)

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implement** `serialize`/`deserialize` (JSON of `entries`, file kept as `fileB64`; never store a live `File`), plus the reactive singleton:

```javascript
import { reactive, computed } from 'vue'
const LS_KEY = 'mirofish_pipeline_queue'

export function serialize(q) { return JSON.stringify({ entries: q.entries }) }
export function deserialize(json) {
  try { const o = JSON.parse(json); return { entries: Array.isArray(o.entries) ? o.entries : [] } }
  catch { return makeQueue() }
}

const _state = reactive({ q: (typeof localStorage !== 'undefined' && localStorage.getItem(LS_KEY))
  ? deserialize(localStorage.getItem(LS_KEY)) : makeQueue() })

function persist() {
  if (typeof localStorage !== 'undefined') localStorage.setItem(LS_KEY, serialize(_state.q))
}
function mutate(fn) { _state.q = fn(_state.q); persist() }

// Generic field patch — used to persist intermediate ids as they are
// learned (projectId, buildTaskId, graphId, realSimId) so a hard-refresh
// mid-pipeline can RESUME instead of restarting (R8; prevents a 2nd graph build).
function patchEntry(q, id, patch) {
  return { entries: q.entries.map(e => e._tmpId === id ? { ...e, ...patch } : e) }
}

export const pipelineStore = {
  entries: computed(() => _state.q.entries),
  active: computed(() => activeEntry(_state.q)),
  capacityFull: computed(() => capacityFull(_state.q)),
  add: (entry) => mutate(q => enqueue(q, entry)),
  setStatus: (id, s) => mutate(q => advanceStatus(q, id, s)),
  setSimId: (id, sid) => mutate(q => backfillSimId(q, id, sid)),
  patch: (id, p) => mutate(q => patchEntry(q, id, p)),   // {projectId, buildTaskId, graphId}
  cancel: (id) => mutate(q => cancel(q, id)),
  remove: (id) => mutate(q => remove(q, id)),
  promoteHead: () => { const h = headToPromote(_state.q); if (h) mutate(q => advanceStatus(q, h._tmpId, FIRST_ACTIVE)); return h },
  raw: () => _state.q,
}
```

**Persisted entry schema (R8, expanded per review):** each entry now carries
the intermediate ids as they are learned, so resume never restarts a
completed step:
`{ _tmpId, prompt, fileB64, fileName, fileType, mode, createdAt, status,
   projectId, buildTaskId, graphId, realSimId }`.
`projectId` set after ontology, `buildTaskId` after buildGraph (non-reused),
`graphId` after build/reuse, `realSimId` after create.

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** — `git commit -am "feat: pipeline store reactive singleton + localStorage persistence (R8)"`

---

## Task 4: app-level driver (auto-pilot only), sequence via mocked API (TDD)

The driver advances the active auto-pilot submission through the endpoint sequence, then promotes the next. Written so the sequence is testable with an injected api object.

**Files:**
- Create: `frontend/src/services/pipelineDriver.js`
- Test: `frontend/tests/pipelineDriver.test.mjs`

Sequence (from spec Q2, verified against Step pages). API names confirmed
in `frontend/src/api/graph.js` + `simulation.js`:
1. `ontology`: `generateOntology(formData)` → `project_id` → `store.patch(id,{projectId})`.
   **FormData contract** (from `MainView.vue:210-214`): append each file as
   `formData.append('files', file)` (repeated) + `formData.append('simulation_requirement', prompt)`.
2. `building`: `buildGraph({project_id})` → returns `{reused, graph_id}` (skip poll)
   OR `{task_id}` → `store.patch(id,{buildTaskId})` → poll `getTaskStatus(task_id)`
   every 2s until `status==='completed'` → `getProject(project_id)` → `graph_id`
   → `store.patch(id,{graphId})`.
3. `creating`: `createSimulation({project_id, graph_id, enable_twitter:true, enable_reddit:true})`
   → `simulation_id` → **`store.setSimId(id, simulation_id)`**.
4. `preparing`: `prepareSimulation({simulation_id, use_llm_for_profiles:true, parallel_profile_count:5})`
   → `{task_id}` or `{already_prepared}` → poll **`getPrepareStatus({task_id, simulation_id})`**
   until prepared (`status ∈ completed/ready`).
5. `running`: `startSimulation({simulation_id, platform:'parallel', force:true})`
   → poll `getRunStatus(simulation_id)` until `runner_status ∈ {completed, stopped, failed}`.
6. on terminal → `store.setStatus(id,'done')` → `promoteHead()` → recurse.

**Per-status RESUME (R8, prevents duplicate graph build on mid-build refresh):**
on rehydrate, `runOne` branches on the entry's `status` + stored ids, it does
NOT restart from step 1:
- `ontology` (no `projectId`) → restart step 1 (nothing persisted yet — safe, no server work done).
- `building` with `buildTaskId` → resume polling that task; with `graphId` → skip to create.
- `creating`/`preparing`/`running` with `realSimId` → resume from that step (poll
  `getPrepareStatus`/`getRunStatus`), never re-create.

**Re-entrancy guard (prevents double `/start` = the OOM):** the driver keeps an
in-memory `inFlight = new Set()` of `_tmpId`s currently being run. `startDriver`'s
tick refuses to `runOne` an entry already in `inFlight`. `runOne` adds on entry,
removes in `finally`.

- [ ] **Step 1: Failing test — driver runs the sequence for one auto entry (mocked, instant)**

```javascript
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { runOne } from '../src/services/pipelineDriver.js'

function mockApi(calls) {
  return {
    generateOntology: async () => (calls.push('ontology'), { data: { project_id: 'proj_1' } }),
    buildGraph: async () => (calls.push('build'), { data: { reused: true, graph_id: 'g1' } }),
    getProject: async () => ({ data: { graph_id: 'g1' } }),
    createSimulation: async () => (calls.push('create'), { data: { simulation_id: 'sim_1' } }),
    prepareSimulation: async () => (calls.push('prepare'), { data: { task_id: 'pt1' } }),
    getPrepareStatus: async () => ({ data: { status: 'completed' } }),
    startSimulation: async () => (calls.push('start'), { data: { runner_status: 'running' } }),
    getRunStatus: async () => ({ data: { runner_status: 'completed' } }),
  }
}
// non-reused build path: buildGraph returns a task, poll then getProject
function mockApiPolling(calls) {
  const base = mockApi(calls)
  return { ...base,
    buildGraph: async () => (calls.push('build'), { data: { task_id: 'bt1' } }),
    getTaskStatus: async () => ({ data: { status: 'completed' } }),
    getProject: async () => ({ data: { graph_id: 'g1' } }) }
}

test('runOne advances an entry through the full sequence and backfills sim id', async () => {
  const calls = []
  const store = { setStatus() {}, setSimId(id, sid) { store._sid = sid }, patch() {} }
  const entry = { _tmpId: 't1', file: {}, prompt: 'p' }
  await runOne(entry, { api: mockApi(calls), store, sleep: async () => {}, signal: () => {}, buildFormData: () => ({}) })
  assert.deepEqual(calls, ['ontology', 'build', 'create', 'prepare', 'start'])
  assert.equal(store._sid, 'sim_1')
})

test('runOne polls the non-reused build task + prepare task', async () => {
  const calls = []
  const store = { setStatus() {}, setSimId() {}, patch() {} }
  await runOne({ _tmpId: 't2', file: {}, prompt: 'p' },
    { api: mockApiPolling(calls), store, sleep: async () => {}, signal: () => {}, buildFormData: () => ({}) })
  assert.deepEqual(calls, ['ontology', 'build', 'create', 'prepare', 'start'])
})

test('a second tick does not re-enter runOne for an in-flight entry', async () => {
  // startDriver must guard by _tmpId; simulate two ticks racing one entry
  const calls = []
  const api = mockApi(calls)
  let resolveOnto
  api.generateOntology = () => new Promise(r => { resolveOnto = () => r({ data: { project_id: 'proj_1' } }) })
  const inFlight = new Set()
  const entry = { _tmpId: 't3', mode: 'auto', file: {}, prompt: 'p' }
  const store = { setStatus() {}, setSimId() {}, patch() {} }
  const deps = { api, store, sleep: async () => {}, signal: () => {}, buildFormData: () => ({}) }
  const p1 = runOne(entry, deps, inFlight)   // enters, adds t3, awaits ontology
  const p2 = runOne(entry, deps, inFlight)   // must no-op (t3 already in flight)
  resolveOnto()
  await Promise.all([p1, p2])
  assert.equal(calls.filter(c => c === 'ontology').length, 1)   // ontology called once, not twice
})
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implement `runOne(entry, deps, inFlight)`** — deps = `{api, store, sleep, signal, buildFormData}`. Guard: if `inFlight.has(entry._tmpId)` return immediately; else `inFlight.add`; `finally` `inFlight.delete`. Advance status + persist ids at each stage (`store.setStatus`, `store.patch`, `store.setSimId`), poll where async (`getTaskStatus`, `getPrepareStatus`, `getRunStatus`) using injected `sleep`. Emit `signal()` on each transition (R3). Handle `reused` graph (skip poll). **Resume branches** per stored `status`+ids (R8). Wrap in try/catch → `store.setStatus(failed)`.
  Also export `startDriver(deps)` — an interval loop holding one module-level `inFlight = new Set()`: if `pipelineStore.active` is an **auto** entry, `runOne(active, deps, inFlight)`; else if nothing active AND no manual sim is running (`/api/status.running_simulations` empty), `promoteHead()` then run it. Manual entries (`entry.mode === 'manual'`) are never driven here (R6).
  Imports: `generateOntology, buildGraph, getTaskStatus, getProject` from `api/graph`; `createSimulation, prepareSimulation, getPrepareStatus, startSimulation, getRunStatus, getSystemStatus` from `api/simulation`.

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** — `git commit -am "feat: app-level pipeline driver (auto-pilot sequence, promote next)"`

---

## Task 5: mount driver once in App.vue

**Files:** Modify `frontend/src/App.vue`

- [ ] **Step 1:** In `App.vue` `<script setup>`, `import { startDriver } from './services/pipelineDriver'` and call it in `onMounted` with the real api + `pipelineStore` + a real `sleep`. It runs for the whole tab lifetime.
- [ ] **Step 2:** Manual check: `npm run build` succeeds; app boots with no console error.
- [ ] **Step 3: Commit** — `git commit -am "feat: start pipeline driver at app root (survives navigation)"`

---

## Task 6: Home submit → instant card + gating

**Files:** Modify `frontend/src/views/Home.vue`

- [ ] **Step 1:** In `startSimulation` (manual) and `startAutoRun` (auto): build an entry `{ _tmpId: tmp_<n>, file, prompt, mode: 'auto'|'manual', createdAt }`, `await fileToB64` → set `fileB64/fileName/fileType`, `pipelineStore.add(entry)`. This creates the instant card immediately.
  - **auto:** stay on Home (do NOT `router.push`); the driver picks it up.
  - **manual:** keep existing `router.push` into the step flow (Step pages drive it); the entry is `mode:'manual'` so the driver skips advancement but still counts the slot.
- [ ] **Step 2:** Replace the `capacityFull` source: disable start section when `pipelineStore.capacityFull.value` (store is the synchronous gate, R5). Keep the existing `/api/status.capacity_full` poll as a secondary guard.
  - Below capacity but slot occupied → a click still `add`s (becomes `queued`), does NOT start — the store's `enqueue` handles this (only head is active).
- [ ] **Step 3:** Manual check: `npm run build` OK.
- [ ] **Step 4: Commit** — `git commit -am "feat: Home submit enqueues instant card; store-gated start section"`

---

## Task 7: HistoryDatabase — merged list, temp-id key, 运行中 + 生成中 badges

**Files:** Modify `frontend/src/components/HistoryDatabase.vue`

- [ ] **Step 1:** Replace `projects` render source with a computed `displayProjects = mergeForDisplay(serverProjects.value, pipelineStore.raw())`. Card `:key="project.simulation_id || project._tmpId"` (R1).
- [ ] **Step 2:** Badges:
  - 运行中 (green) when `isCardRunning(project)` (id ∈ running_simulations — already wired) OR `project.status === 'running'`.
  - 生成中 (blue) when `project._optimistic && ['ontology','building','creating','preparing'].includes(project.status)`.
  - 排队中 (existing) when `isCardQueued` OR `project.status === 'queued'` (store precedence, R4).
- [ ] **Step 3:** 取消排队 on optimistic `queued` cards → `pipelineStore.cancel(project._tmpId)`.
- [ ] **Step 4:** History re-fetch trigger (R3): subscribe to the driver `signal` (e.g. a shared reactive `driverTick` ref bumped on each transition) → `watch(driverTick, loadHistory)`. Keep a low-freq safety reload.
- [ ] **Step 5:** Clicking an optimistic pre-sim card → route to live view only if `realSimId` exists, else no-op (R7).
- [ ] **Step 6:** Manual check: `npm run build` OK; add a locale string `history.generating` = 生成中 / "Generating" (en+zh).
- [ ] **Step 7: Commit** — `git commit -am "feat: history cards merge optimistic entries + 运行中/生成中 badges"`

---

## Task 7b: manual entry releases its slot (R6 — critical)

Without this, a manual submit leaves a permanent active store entry → the
driver never promotes queued items and gating jams. Two hooks so the manual
Step flow writes its lifecycle back to the store.

**Files:**
- Modify: `frontend/src/components/Step1GraphBuild.vue` (after `createSimulation` returns a `simulation_id`)
- Modify: `frontend/src/components/Step3Simulation.vue` (on terminal run status)
- Modify: `frontend/src/services/pipelineDriver.js` (driver-side safety reconcile)
- Test: `frontend/tests/pipelineQueue.test.mjs` (reconcileManual pure helper)

- [ ] **Step 1: Failing test for a pure `reconcileManual(q, runningIds)` helper** — a manual entry whose `realSimId` is NOT in `runningIds` AND has been started (status `running`) is marked `done` (frees slot). A manual entry still running stays.

```javascript
test('reconcileManual marks a finished manual entry done', () => {
  let q = makeQueue()
  q = enqueue(q, { _tmpId: 'm', mode: 'manual', status: 'queued' })
  q = advanceStatus(q, 'm', 'running')
  q = backfillSimId(q, 'm', 'sim_m')
  assert.equal(reconcileManual(q, []).entries[0].status, 'done')       // not running anymore
  assert.equal(reconcileManual(q, ['sim_m']).entries[0].status, 'running') // still running
})
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implement** `reconcileManual(q, runningIds)` (pure) in `pipelineQueue.js`; export `pipelineStore.reconcileManual(runningIds)`. In the driver's tick, after reading `/api/status`, call `store.reconcileManual(running_simulations)` so a completed manual frees the slot. In `Step1GraphBuild.vue`, when a manual create returns, `pipelineStore.setSimId(tmpId, simulation_id)` + `patch({projectId, graphId})` (the manual entry's `_tmpId` is passed via route/query or a lookup by the just-created sim). In `Step3Simulation.vue` terminal, `pipelineStore.setStatus(tmpId,'done')`. (If wiring the exact `_tmpId` through the manual pages is fragile, the driver-side `reconcileManual` alone is sufficient to free the slot — the Step hooks are the faster path, reconcile is the safety net.)

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** — `git commit -am "feat: manual entries free the pipeline slot (reconcile via /api/status)"`

---

## Task 8: live verification + one deploy

- [ ] **Step 1:** `cd frontend && node --test tests/*.mjs` — all pass. `npm run build` — clean.
- [ ] **Step 2:** `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q` — still 103 pass (no backend change).
- [ ] **Step 3:** Manual/live: with the current live run finished, verify on the Space (after deploy): click auto → instant 生成中 card on Home; navigate away + back → card persists; hard refresh → card persists (localStorage); running sim shows 运行中; a 2nd click → 排队中; finishing the active → queued auto-starts. **Screenshot / status-verify before claiming done.**
- [ ] **Step 4:** Merge to main; **one** safe deploy (`bash scripts/deploy_hf.sh` — auto-waits if busy, backs up, restores). Do NOT deploy mid-task.
- [ ] **Step 5:** Delete branch after merge.

---

## Notes for the implementer

- **Never touch `backend/**` orchestration.** The backend run-queue must stay dormant (Task 6 gating guarantees no 2nd concurrent `/start`).
- The driver advances **auto** entries only; **manual** entries are slot-occupying but driven by their Step pages (R6). Guard `runOne` with `entry.mode === 'auto'`.
- Base64 file in localStorage is fine for ~35KB docx; if a future large upload appears, cap and fall back to in-memory only (out of scope now).
- Verify live before any "done" claim — evidence, not assertion.
