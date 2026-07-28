// App-level pipeline driver. Advances one auto-pilot submission through
// the existing endpoints (ontology -> build -> create -> prepare -> run),
// then the next. `runOne` is pure/deps-injected (no top-level api/vue/store
// imports) so it is unit-testable under node --test. `startDriver` wires the
// real store + api via dynamic import at call time.
import { b64ToFile } from '../store/fileCodec.js'

const TERMINAL_RUN = ['completed', 'stopped', 'failed']
const PREPARED = ['completed', 'ready']

// Advance a single entry. Guarded by `inFlight` (per _tmpId) so a second
// driver tick can never re-enter and double-fire /start (the OOM). Resumes
// from stored ids — never restarts a step whose output id already exists.
export async function runOne(entry, deps, inFlight = new Set()) {
  const id = entry._tmpId
  if (inFlight.has(id)) return
  inFlight.add(id)
  const { api, store, sleep, signal, buildFormData } = deps
  try {
    let projectId = entry.projectId
    let graphId = entry.graphId
    let simId = entry.realSimId

    if (!projectId) {
      const res = await api.generateOntology(buildFormData(entry))
      projectId = (res.data || res).project_id
      store.patch(id, { projectId }); store.setStatus(id, 'building'); signal()
    }

    if (!graphId) {
      const d = (await api.buildGraph({ project_id: projectId })).data || {}
      if (d.graph_id) {
        graphId = d.graph_id
      } else if (d.task_id) {
        store.patch(id, { buildTaskId: d.task_id })
        while (((await api.getTaskStatus(d.task_id)).data || {}).status !== 'completed') { await sleep(2000) }
        graphId = ((await api.getProject(projectId)).data || {}).graph_id
      }
      store.patch(id, { graphId }); store.setStatus(id, 'creating'); signal()
    }

    if (!simId) {
      const res = await api.createSimulation({ project_id: projectId, graph_id: graphId, enable_twitter: true, enable_reddit: true })
      simId = (res.data || res).simulation_id
      store.setSimId(id, simId); store.setStatus(id, 'preparing'); signal()
    }

    // prepare (idempotent server-side: already_prepared short-circuits)
    {
      const d = (await api.prepareSimulation({ simulation_id: simId, use_llm_for_profiles: true, parallel_profile_count: 5 })).data || {}
      if (!d.already_prepared && d.task_id) {
        let s
        do {
          s = ((await api.getPrepareStatus({ task_id: d.task_id, simulation_id: simId })).data || {}).status
          if (!PREPARED.includes(s)) await sleep(2000)
        } while (!PREPARED.includes(s))
      }
      signal()
    }

    // run
    {
      await api.startSimulation({ simulation_id: simId, platform: 'parallel', force: true })
      // NOTE: the entry stays 'preparing' until the run is OBSERVED live.
      // Marking it 'running' before then let the server-side reconcile see a
      // "running entry with no live run" and delete the card mid-pipeline.
      // The backend may also legitimately QUEUE this start (slot busy), so we
      // wait patiently and only treat "gone" as fatal AFTER it has been live.
      let rs
      let wasLive = false
      let goneStreak = 0
      do {
        rs = ((await api.getRunStatus(simId)).data || {}).runner_status
        if (TERMINAL_RUN.includes(rs)) break
        let live = []
        try { live = ((await api.getSystemStatus()).data || {}).running_simulations || [] } catch { /* ignore */ }
        const isLive = live.includes(simId) || rs === 'running'
        if (isLive && !wasLive) {
          wasLive = true
          store.setStatus(id, 'running'); signal()   // only now is it truly running
        }
        if (wasLive) {
          // A restart kills the subprocess but leaves run_state stuck on
          // 'running' forever — bail instead of polling a corpse.
          goneStreak = live.includes(simId) ? 0 : goneStreak + 1
          if (goneStreak >= 5) throw new Error('simulation process is gone (killed or restarted)')
        }
        await sleep(2000)
      } while (true)
    }

    // report (Step 4) — auto-pilot means "auto to report", so the driver
    // kicks report generation after the run. Best-effort: a report failure
    // does not fail the whole pipeline (the run + graph still succeeded).
    {
      store.setStatus(id, 'reporting'); signal()
      try {
        await api.generateReport({ simulation_id: simId, force_regenerate: true })
      } catch (e) { /* report is best-effort */ }
      store.setStatus(id, 'done'); signal()
    }
  } catch (e) {
    store.setStatus(id, 'failed'); signal()
  } finally {
    inFlight.delete(id)
  }
}

// Reconstruct FormData for the ontology call from the (persisted) entry.
export function buildFormData(entry) {
  const fd = new FormData()
  const file = entry.file || b64ToFile({ b64: entry.fileB64, name: entry.fileName, type: entry.fileType })
  fd.append('files', file)
  fd.append('simulation_requirement', entry.prompt)
  return fd
}

const _inFlight = new Set()
let _started = false

// One sync pass: pull server truth, reconcile/prune, push local changes.
// Steps 1-4 ONLY — the advance logic (runOne/promoteHead) stays in the
// interval callback so runOne is never awaited here (awaiting it would hold
// the tick for the whole pipeline). Deps-injected so it is unit-testable.
export async function syncTick({ store, pipeApi, api, toServerEntry }) {
  // 1. pull server truth + merge (server owns status/membership)
  try {
    const r = await pipeApi.getPipeline()
    store.applyServerMerge(((r.data || r).entries) || [])
  } catch { /* offline: keep local, retry next tick */ }

  // 2. reconcile manual runs, then prune (prune tombstones what it drops)
  try {
    const st = (await api.getSystemStatus()).data || {}
    store.reconcileManual(st.running_simulations || [])
  } catch { /* ignore */ }
  store.prune()

  // 3. push dirty entries AFTER reconcile, so a manual run's 'done' ships
  for (const e of store.dirtyEntries()) {
    const rev = e._rev
    try {
      await pipeApi.putPipelineEntry(toServerEntry(e))
      store.markClean(e._tmpId, rev)
    } catch { /* retry next tick */ }
  }

  // 4. retry outstanding deletes (tombstones)
  for (const t of store.pendingTombstones()) {
    try {
      await pipeApi.deletePipelineEntry(t.tmpId)
      store.ackTombstone(t.tmpId)
    } catch { /* retry next tick */ }
  }
}

// Mount once at app root. Dynamic-imports store + api so this module stays
// unit-testable (runOne/syncTick above pull nothing heavy).
export async function startDriver() {
  if (_started) return
  _started = true
  const { pipelineStore, toServerEntry } = await import('../store/pipelineQueue.js')
  const graph = await import('../api/graph.js')
  const sim = await import('../api/simulation.js')
  const report = await import('../api/report.js')
  const pipeApi = await import('../api/pipeline.js')
  const api = { ...graph, ...sim, ...report }
  const sleep = (ms) => new Promise(r => setTimeout(r, ms))
  const signal = () => { bumpTick() }
  const deps = { api, store: pipelineStore, sleep, signal, buildFormData }
  const store = pipelineStore

  // initial hydration so a refresh shows the server's queue immediately
  try {
    const r = await pipeApi.getPipeline()
    store.applyServerMerge(((r.data || r).entries) || [])
  } catch { /* offline */ }

  // Re-entrancy guard: the tick now awaits several calls; without this a slow
  // tick would overlap itself (duplicate writes, stale merges landing late).
  let tickBusy = false
  setInterval(async () => {
    if (tickBusy) return
    tickBusy = true
    try {
      await syncTick({ store, pipeApi, api, toServerEntry })

      // advance (NOT awaited — runOne runs for minutes; awaiting it would
      // hold tickBusy and starve the sync above). Display-only entries have
      // no file bytes in this browser, so they are never driven.
      const active = store.active.value
      if (active && active.mode === 'auto' && !active._displayOnly) {
        runOne(active, deps, _inFlight); return
      }
      if (!active) {
        const h = store.promoteHead()
        if (h && h.mode === 'auto' && !h._displayOnly) {
          runOne({ ...h, status: 'ontology' }, deps, _inFlight)
        }
      }
    } finally {
      tickBusy = false
    }
  }, 3000)
}

// R3: history re-fetch trigger. Components watch driverTick and reload.
import { ref } from 'vue'
export const driverTick = ref(0)
function bumpTick() { driverTick.value++ }
