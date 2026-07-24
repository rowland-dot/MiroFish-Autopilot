// Pipeline queue — frontend-owned concurrency control.
// slot=1 active + queue=2 waiting = capacity 3. One project (whole
// pipeline: ontology -> build -> create -> prepare -> run) at a time.
// Pure functions first, then a reactive singleton + localStorage layer.
import { reactive, computed } from 'vue'

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
  if (isFull(q)) return q
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

// Set status on the entry matching a real simulation_id (Step pages know the
// sim id, not the temp id). Used to release a manual entry's slot.
export function advanceBySimId(q, realSimId, status) {
  return { entries: q.entries.map(e => e.realSimId === realSimId ? { ...e, status } : e) }
}

export function patchEntry(q, tmpId, patch) {
  return { entries: q.entries.map(e => e._tmpId === tmpId ? { ...e, ...patch } : e) }
}

export function cancel(q, tmpId) { return remove(q, tmpId) }
export function remove(q, tmpId) {
  return { entries: q.entries.filter(e => e._tmpId !== tmpId) }
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
    .filter(e => e.status !== 'done')
    .filter(e => !(e.realSimId && serverIds.has(e.realSimId)))
    .map(e => ({
      _optimistic: true, _tmpId: e._tmpId, simulation_id: e.realSimId || null,
      status: e.status, files: [{ filename: e.fileName }],
      simulation_requirement: e.prompt, created_at: e.createdAt,
    }))
  return [...optimistic, ...serverList]
}

// ---- persistence (R8: survive hard refresh) ----
const LS_KEY = 'mirofish_pipeline_queue'

export function serialize(q) { return JSON.stringify({ entries: q.entries }) }
export function deserialize(json) {
  try { const o = JSON.parse(json); return { entries: Array.isArray(o.entries) ? o.entries : [] } }
  catch { return makeQueue() }
}

// ---- reactive singleton ----
const _state = reactive({
  q: (typeof localStorage !== 'undefined' && localStorage.getItem(LS_KEY))
    ? deserialize(localStorage.getItem(LS_KEY))
    : makeQueue(),
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
  promoteHead: () => {
    const h = headToPromote(_state.q)
    if (h) mutate(q => advanceStatus(q, h._tmpId, 'ontology'))
    return h
  },
  raw: () => _state.q,
}

