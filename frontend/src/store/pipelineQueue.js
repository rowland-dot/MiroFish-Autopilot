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

// Display-only entries (hydrated from the server in a browser without their
// file bytes) never hold the slot and are never driven — otherwise another
// browser's entries would deadlock this one's queue. Safe because the backend
// enforces slot=1/queue=2 for OASIS runs itself (services/simulation_queue.py).
const drivable = (e) => !e._displayOnly

function activeCount(q) { return q.entries.filter(e => drivable(e) && ACTIVE_STATUSES.includes(e.status)).length }
function queuedCount(q) { return q.entries.filter(e => drivable(e) && e.status === 'queued').length }

export function activeEntry(q) { return q.entries.find(e => drivable(e) && ACTIVE_STATUSES.includes(e.status)) || null }
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
  return q.entries.find(e => drivable(e) && e.status === 'queued') || null
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
  const live = q.entries.filter(e => e.status !== 'done' && e.status !== 'failed')
  const serverIds = new Set(serverList.map(r => r.simulation_id))

  // still-optimistic entries: no server record yet
  const optimistic = live
    .filter(e => !(e.realSimId && serverIds.has(e.realSimId)))
    .map(e => ({
      _optimistic: true, _tmpId: e._tmpId, simulation_id: e.realSimId || null,
      _projectId: e.projectId || null,
      status: e.status, files: [{ filename: e.fileName }],
      simulation_requirement: e.prompt, created_at: e.createdAt,
    }))

  // Once the sim record exists server-side we show the REAL record — but keep
  // its live pipeline status attached, else the card loses its badge and falls
  // back to server sort order while the pipeline is still mid-flight.
  const bySimId = new Map(live.filter(e => e.realSimId).map(e => [e.realSimId, e]))
  const annotated = serverList.map(r => {
    const e = bySimId.get(r.simulation_id)
    if (!e) return r
    return {
      ...r,
      _pipelineStatus: e.status, _tmpId: e._tmpId, _projectId: e.projectId || null,
      // 服务器记录在 prepare 写入配置前没有 simulation_requirement/文件名，
      // 卡片会显示「未命名模拟」——用流水线条目里的提示词/文件名补上
      simulation_requirement: r.simulation_requirement || e.prompt || '',
      files: (r.files && r.files.length) ? r.files
        : (e.fileName ? [{ filename: e.fileName }] : (r.files || [])),
    }
  })
  const inFlight = annotated.filter(r => r._pipelineStatus)
  const rest = annotated.filter(r => !r._pipelineStatus)

  // Order by PIPELINE STAGE, not by bucket: an active job must sit ahead of a
  // queued one even though the queued card is still "optimistic" (no server
  // record) while the active one has already become a real record.
  const stageOf = (c) => c._optimistic ? c.status : c._pipelineStatus
  const rank = (c) => {
    const s = stageOf(c)
    if (ACTIVE_STATUSES.includes(s)) return 0     // running / preparing / ... first
    if (s === 'queued') return 1                  // then waiting
    return 2
  }
  const pipelineCards = [...optimistic, ...inFlight].sort((a, b) => rank(a) - rank(b))
  return [...pipelineCards, ...rest]
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
    reportId: e.reportId || null,
    prompt: e.prompt, fileName: e.fileName, createdAt: e.createdAt,
  }
}

const SERVER_OWNED = ['status', 'projectId', 'graphId', 'buildTaskId', 'reportId', 'mode', 'prompt', 'fileName', 'createdAt']

function fromServerEntry(s) {
  return {
    _tmpId: s.tmpId, mode: s.mode, status: s.status,
    realSimId: s.simId || null, projectId: s.projectId || null,
    graphId: s.graphId || null, buildTaskId: s.buildTaskId || null,
    reportId: s.reportId || null,
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

// Persist must never throw: a few-MB upload becomes ~1.33x as base64 and can
// blow the ~5MB localStorage quota. If it does, retry WITHOUT the file bytes
// (the queue/status still survives a refresh; only this browser's ability to
// drive that entry is lost) rather than breaking every store mutation.
function persist() {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(LS_KEY, serialize(_state.q))
  } catch {
    try {
      const lean = {
        ...(_state.q),
        entries: _state.q.entries.map(({ fileB64, file, ...rest }) => rest),
      }
      localStorage.setItem(LS_KEY, serialize(lean))
    } catch { /* give up on persistence; in-memory state still works */ }
  }
}

// Mark an entry dirty (unacked local change) and bump its revision, so a
// server response that raced the change cannot roll it back, and a stale
// POST ack cannot clear a newer change.
function markDirty(q, tmpId) {
  if (!tmpId) return q
  return {
    ...q,
    entries: q.entries.map(e => e._tmpId === tmpId
      ? { ...e, _dirty: true, _rev: (e._rev || 0) + 1 }
      : e),
  }
}

function mutate(fn, dirtyId) {
  let next = fn(_state.q)
  if (dirtyId) next = markDirty(next, dirtyId)
  _state.q = next
  persist()
}

function addTombstones(q, ids) {
  const have = new Set((q.tombstones || []).map(t => t.tmpId))
  const added = ids.filter(id => id && !have.has(id))
    .map(id => ({ tmpId: id, _deleted: true, _ackedAt: null }))
  return { ...q, tombstones: [...(q.tombstones || []), ...added] }
}

const simIdToTmp = (q, simId) => (q.entries.find(e => e.realSimId === simId) || {})._tmpId

export const pipelineStore = {
  entries: computed(() => _state.q.entries),
  active: computed(() => activeEntry(_state.q)),
  capacityFull: computed(() => capacityFull(_state.q)),

  // A brand-new entry is revision 0 and already unacked — no extra bump.
  add: (entry) => mutate(q => enqueue(q, { ...entry, _rev: 0, _dirty: true, _seenOnServer: false })),
  setStatus: (id, s) => mutate(q => advanceStatus(q, id, s), id),
  setSimId: (id, sid) => mutate(q => backfillSimId(q, id, sid), id),
  setStatusBySimId: (sid, s) => mutate(q => advanceBySimId(q, sid, s), simIdToTmp(_state.q, sid)),
  patch: (id, p) => mutate(q => patchEntry(q, id, p), id),
  reconcileManual: (runningIds) => {
    // mark every entry this flips to done as dirty, so the status reaches the server
    const flipped = _state.q.entries
      .filter(e => e.mode === 'manual' && e.status === 'running' && e.realSimId
                   && !(runningIds || []).includes(e.realSimId))
      .map(e => e._tmpId)
    mutate(q => flipped.reduce((acc, id) => markDirty(acc, id), reconcileManual(q, runningIds)))
  },

  // Removal always leaves a tombstone: it suppresses a stale server copy and
  // the driver retries the DELETE until the server converges.
  cancel: (id) => mutate(q => addTombstones(cancel(q, id), [id])),
  remove: (id) => mutate(q => addTombstones(remove(q, id), [id])),
  prune: () => mutate(q => {
    const dropped = q.entries.filter(e => e.status === 'done' || e.status === 'failed').map(e => e._tmpId)
    return addTombstones(pruneFinished(q), dropped)
  }),

  promoteHead: () => {
    const h = headToPromote(_state.q)
    if (h) mutate(q => advanceStatus(q, h._tmpId, 'ontology'), h._tmpId)
    return h
  },

  // ---- server sync ----
  applyServerMerge: (serverEntries) => mutate(q => mergeServerEntries(q, serverEntries)),
  dirtyEntries: () => _state.q.entries.filter(e => e._dirty),
  tombstones: () => _state.q.tombstones || [],
  pendingTombstones: () => (_state.q.tombstones || []).filter(t => !t._ackedAt),
  markClean: (tmpId, rev) => mutate(q => ({
    ...q,
    entries: q.entries.map(e => (e._tmpId === tmpId && e._rev === rev) ? { ...e, _dirty: false } : e),
  })),
  ackTombstone: (tmpId) => mutate(q => ({
    ...q,
    tombstones: (q.tombstones || []).map(t => t.tmpId === tmpId ? { ...t, _ackedAt: Date.now() } : t),
  })),

  reset: () => { _state.q = makeQueue(); persist() },   // test helper
  raw: () => _state.q,
}

