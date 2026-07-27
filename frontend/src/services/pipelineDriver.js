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
      store.setStatus(id, 'running'); signal()
    }

    // run
    {
      await api.startSimulation({ simulation_id: simId, platform: 'parallel', force: true })
      let rs
      do {
        rs = ((await api.getRunStatus(simId)).data || {}).runner_status
        if (!TERMINAL_RUN.includes(rs)) await sleep(2000)
      } while (!TERMINAL_RUN.includes(rs))
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

// Mount once at app root. Dynamic-imports store + api so this module stays
// unit-testable (runOne above pulls nothing heavy).
export async function startDriver() {
  if (_started) return
  _started = true
  const { pipelineStore, driverTick } = await import('../store/pipelineQueue.js').then(async m => ({
    pipelineStore: m.pipelineStore, driverTick: null,
  }))
  const graph = await import('../api/graph.js')
  const sim = await import('../api/simulation.js')
  const api = { ...graph, ...sim }
  const sleep = (ms) => new Promise(r => setTimeout(r, ms))
  const signal = () => { bumpTick() }
  const deps = { api, store: pipelineStore, sleep, signal, buildFormData }

  setInterval(async () => {
    const store = pipelineStore
    try {
      const st = (await api.getSystemStatus()).data || {}
      store.reconcileManual(st.running_simulations || [])
    } catch { /* ignore */ }
    store.prune()   // clear done/failed ghosts so dead cards don't linger
    const active = store.active.value
    if (active && active.mode === 'auto') { runOne(active, deps, _inFlight); return }
    if (!active) {
      const h = store.promoteHead()
      if (h && h.mode === 'auto') runOne({ ...h, status: 'ontology' }, deps, _inFlight)
    }
  }, 3000)
}

// R3: history re-fetch trigger. Components watch driverTick and reload.
import { ref } from 'vue'
export const driverTick = ref(0)
function bumpTick() { driverTick.value++ }
