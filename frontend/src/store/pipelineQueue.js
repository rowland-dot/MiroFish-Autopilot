// Pipeline queue — frontend-owned concurrency control.
// slot=1 active + queue=2 waiting = capacity 3. One project (whole
// pipeline: ontology -> build -> create -> prepare -> run) at a time.
// Pure functions first; the reactive singleton + localStorage layer is
// appended below (Task 3).

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
