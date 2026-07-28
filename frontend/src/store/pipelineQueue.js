// Pipeline queue — frontend-owned concurrency control.
// slot=1 active + queue=2 waiting = capacity 3. One project (whole
// pipeline: ontology -> build -> create -> prepare -> run) at a time.
// Pure functions first, then a reactive singleton + localStorage layer.
import { reactive, computed } from 'vue'

export const ACTIVE_STATUSES = ['ontology', 'building', 'creating', 'preparing', 'running', 'reporting']
const SLOT_LIMIT = 1
const QUEUE_LIMIT = 2
const FIRST_ACTIVE = 'ontology'

export function makeQueue() { return { entries: [], tombstones: [] } }

function activeCount(q) { return q.entries.filter(e => ACTIVE_STATUSES.includes(e.status)).length }
function queuedCount(q) { return q.entries.filter(e => e.status === 'queued').length }

export function activeEntry(q) { return q.entries.find(e => ACTIVE_STATUSES.includes(e.status)) || null }
export function isFull(q) { return activeCount(q) >= SLOT_LIMIT && queuedCount(q) >= QUEUE_LIMIT }
export function capacityFull(q) { return isFull(q) }

export function enqueue(q, entry) {
  if (isFull(q)) return q
  const startActive = activeCount(q) < SLOT_LIMIT
  const e = { ...entry, status: startActive ? FIRST_ACTIVE : 'queued' }
  return { ...q, entries: [...q.entries, e] }
}

export function advanceStatus(q, tmpId, status) {
  return { ...q, entries: q.entries.map(e => e._tmpId === tmpId ? { ...e, status } : e) }
}

export function backfillSimId(q, tmpId, realSimId) {
  return { ...q, entries: q.entries.map(e => e._tmpId === tmpId ? { ...e, realSimId } : e) }
}

// Set status on the entry matching a real simulation_id (Step pages know the
// sim id, not the temp id). Used to release a manual entry's slot.
export function advanceBySimId(q, realSimId, status) {
  return { ...q, entries: q.entries.map(e => e.realSimId === realSimId ? { ...e, status } : e) }
}

export function patchEntry(q, tmpId, patch) {
  return { ...q, entries: q.entries.map(e => e._tmpId === tmpId ? { ...e, ...patch } : e) }
}

export function cancel(q, tmpId) { return remove(q, tmpId) }
export function remove(q, tmpId) {
  return { ...q, entries: q.entries.filter(e => e._tmpId !== tmpId) }
}

export function headToPromote(q) {
  if (activeCount(q) >= SLOT_LIMIT) return null
  return q.entries.find(e => e.status === 'queued') || null
}

// A started manual entry whose sim is no longer running is finished -> done
// (frees the slot). Manual entries are driven by their Step pages, not the
// driver, so this is how their slot gets released.
export function reconcileManual(q, runningIds) {
  const running = new Set(runningIds || [])
  return {
    ...q,
    entries: q.entries.map(e => {
      if (e.mode === 'manual' && e.status === 'running' && e.realSimId && !running.has(e.realSimId)) {
        return { ...e, status: 'done' }
      }
      return e
    }),
  }
}

// Merge server history with optimistic entries. Server record wins; an
// optimistic entry whose realSimId is already in the server list is dropped.
export function mergeForDisplay(serverList, q) {
  const serverIds = new Set(serverList.map(r => r.simulation_id))
  const optimistic = q.entries
    .filter(e => e.status !== 'done' && e.status !== 'failed')   // drop finished + dead ghosts
    .filter(e => !(e.realSimId && serverIds.has(e.realSimId)))
    .map(e => ({
      _optimistic: true, _tmpId: e._tmpId, simulation_id: e.realSimId || null,
      _projectId: e.projectId || null,
      status: e.status, files: [{ filename: e.fileName }],
      simulation_requirement: e.prompt, created_at: e.createdAt,
    }))
  return [...optimistic, ...serverList]
}

// Drop finished/dead entries so they don't linger in localStorage as ghosts.
export function pruneFinished(q) {
  return { ...q, entries: q.entries.filter(e => e.status !== 'done' && e.status !== 'failed') }
}

// ---- persistence (R8: survive hard refresh) ----
const LS_KEY = 'mirofish_pipeline_queue'

export function serialize(q) { return JSON.stringify({ entries: q.entries, tombstones: q.tombstones || [] }) }
export function deserialize(json) {
  try {
    const o = JSON.parse(json)
    return {
      entries: Array.isArray(o.entries) ? o.entries : [],
      tombstones: Array.isArray(o.tombstones) ? o.tombstones : [],
    }
  } catch { return makeQueue() }
}

// ---- server sync (pure; the driver injects the api) ----
// 服务器只存状态/成员关系；文件字节始终只在本地 localStorage。
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
    if (tombById.has(l._tmpId)) continue                   // rule 5: tombstone wins
    const s = byId.get(l._tmpId)
    if (!s) {
      // rule 4: drop only if seen-then-missing; rule 6: dirty wins
      if (l._seenOnServer && !l._dirty) continue
      out.push(l); continue
    }
    if (l._dirty) { out.push({ ...l, _seenOnServer: true }); continue }   // rule 2
    const mapped = fromServerEntry(s)                      // rule 3: field-union
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
  for (const s of serverList) {                            // rule 1: hydrate
    if (localIds.has(s.tmpId) || tombById.has(s.tmpId)) continue
    // no file bytes here -> display-only: never driven, never holds the slot
    out.push({ ...fromServerEntry(s), _displayOnly: true })
  }

  // tombstone clears only after a DELETE ack AND a later response lacking the id
  const kept = tombs.filter(t => !(t._ackedAt && !byId.has(t.tmpId)))
  return { ...q, entries: out, tombstones: kept }
}

// ---- reactive singleton ----
const _state = reactive({
  q: pruneFinished(
    (typeof localStorage !== 'undefined' && localStorage.getItem(LS_KEY))
      ? deserialize(localStorage.getItem(LS_KEY))
      : makeQueue()
  ),   // clear ghosts from a prior session on load
})

function persist() {
  if (typeof localStorage !== 'undefined') localStorage.setItem(LS_KEY, serialize(_state.q))
}
function mutate(fn) { _state.q = fn(_state.q); persist() }

export const pipelineStore = {
  entries: computed(() => _state.q.entries),
  active: computed(() => activeEntry(_state.q)),
  capacityFull: computed(() => capacityFull(_state.q)),
  add: (entry) => mutate(q => enqueue(q, entry)),
  setStatus: (id, s) => mutate(q => advanceStatus(q, id, s)),
  setSimId: (id, sid) => mutate(q => backfillSimId(q, id, sid)),
  setStatusBySimId: (sid, s) => mutate(q => advanceBySimId(q, sid, s)),
  patch: (id, p) => mutate(q => patchEntry(q, id, p)),
  cancel: (id) => mutate(q => cancel(q, id)),
  remove: (id) => mutate(q => remove(q, id)),
  reconcileManual: (runningIds) => mutate(q => reconcileManual(q, runningIds)),
  prune: () => mutate(q => pruneFinished(q)),
  promoteHead: () => {
    const h = headToPromote(_state.q)
    if (h) mutate(q => advanceStatus(q, h._tmpId, 'ontology'))
    return h
  },
  raw: () => _state.q,
}

