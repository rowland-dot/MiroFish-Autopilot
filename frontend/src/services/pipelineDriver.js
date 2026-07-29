// App-level pipeline driver. Advances one auto-pilot submission through
// the existing endpoints (ontology -> build -> create -> prepare -> run),
// then the next. `runOne` is pure/deps-injected (no top-level api/vue/store
// imports) so it is unit-testable under node --test. `startDriver` wires the
// real store + api via dynamic import at call time.
import { b64ToFile } from '../store/fileCodec.js'
import { evaluateLease, leaseValue, LOCK_KEY } from './driverLock.js'

const TERMINAL_RUN = ['completed', 'stopped', 'failed']
const PREPARED = ['completed', 'ready']

// Transient provider/gateway trouble (LLM rate limits, HF gateway flaps)
// must NOT fail the whole job — back off and retry a few times first.
function isTransient(e) {
  const st = e && e.response && e.response.status
  if ([429, 500, 502, 503, 504].includes(st)) return true
  return /HTTP 429|rate limit|Network Error|timeout|ECONNABORTED/i.test((e && e.message) || '')
}

async function withRetry(fn, sleep, attempts = 3) {
  let firstMsg = null
  for (let i = 0; ; i++) {
    try { return await fn() } catch (e) {
      const msg = String((e && e.message) || e)
      if (firstMsg === null) firstMsg = msg
      if (i >= attempts - 1 || !isTransient(e)) {
        // Keep the ROOT CAUSE visible: the last attempt can fail differently
        // (e.g. a 400) and would otherwise mask the rate-limit that actually
        // killed the job — that misleads the user.
        if (firstMsg && firstMsg !== msg) e.message = `${msg}（此前 ${i} 次尝试失败：${firstMsg}）`
        throw e
      }
      await sleep(5000 * (i + 1))
    }
  }
}

// Advance a single entry. Guarded by `inFlight` (per _tmpId) so a second
// driver tick can never re-enter and double-fire /start (the OOM). Resumes
// from stored ids — never restarts a step whose output id already exists.
export async function runOne(entry, deps, inFlight = new Set()) {
  const id = entry._tmpId
  if (inFlight.has(id)) return
  inFlight.add(id)
  const { api, store, sleep, signal, buildFormData } = deps
  // Cancelled mid-flight? The user can 取消 an entry AFTER it was promoted and
  // this runOne started. Without this check the pipeline keeps burning LLM
  // quota (ontology/build/prepare) for a job that no longer exists.
  const isGone = () => {
    try { return store.raw ? !store.raw().entries.some(e => e._tmpId === id) : false }
    catch { return false }
  }
  try {
    let projectId = entry.projectId
    let graphId = entry.graphId
    let simId = entry.realSimId

    if (!projectId) {
      const res = await withRetry(() => api.generateOntology(buildFormData(entry)), sleep)
      projectId = (res.data || res).project_id
      store.patch(id, { projectId }); store.setStatus(id, 'building'); signal()
    }

    if (isGone()) return

    if (!graphId) {
      const d = (await withRetry(() => api.buildGraph({ project_id: projectId }), sleep)).data || {}
      if (d.graph_id) {
        graphId = d.graph_id
      } else if (d.task_id) {
        store.patch(id, { buildTaskId: d.task_id })
        for (;;) {
          if (isGone()) return
          const ts = ((await api.getTaskStatus(d.task_id)).data || {})
          if (ts.status === 'completed') break
          if (ts.status === 'failed') throw new Error('graph build failed: ' + (ts.error || ''))
          await sleep(2000)
        }
        graphId = ((await api.getProject(projectId)).data || {}).graph_id
      }
      store.patch(id, { graphId }); store.setStatus(id, 'creating'); signal()
    }

    if (isGone()) return

    if (!simId) {
      const res = await withRetry(() => api.createSimulation({ project_id: projectId, graph_id: graphId, enable_twitter: true, enable_reddit: true }), sleep)
      simId = (res.data || res).simulation_id
      store.setSimId(id, simId); store.setStatus(id, 'preparing'); signal()
    }

    if (isGone()) return

    // prepare (idempotent server-side: already_prepared short-circuits)
    {
      const d = (await withRetry(() => api.prepareSimulation({ simulation_id: simId, use_llm_for_profiles: true, parallel_profile_count: 5 }), sleep)).data || {}
      if (!d.already_prepared && d.task_id) {
        for (;;) {
          if (isGone()) return
          const ps = ((await api.getPrepareStatus({ task_id: d.task_id, simulation_id: simId })).data || {})
          if (PREPARED.includes(ps.status)) break
          if (ps.status === 'failed') throw new Error('prepare failed: ' + (ps.error || ''))
          await sleep(2000)
        }
      }
      signal()
    }

    if (isGone()) return

    // run
    {
      // Resume guard: a browser refresh re-enters runOne with stored ids.
      // Blindly POSTing start with force:true here RESTARTED an already
      // finished 72/72 run from round 0. Check first: completed -> straight
      // to report; already live -> just poll; only otherwise start.
      const pre = ((await api.getRunStatus(simId)).data || {}).runner_status
      if (pre !== 'completed') {
        if (pre !== 'running') {
          await withRetry(() => api.startSimulation({ simulation_id: simId, platform: 'parallel', force: true }), sleep)
        }
      // NOTE: the entry stays 'preparing' until the run is OBSERVED live.
      // Marking it 'running' before then let the server-side reconcile see a
      // "running entry with no live run" and delete the card mid-pipeline.
      // The backend may also legitimately QUEUE this start (slot busy), so we
      // wait patiently and only treat "gone" as fatal AFTER it has been live.
      let rs
      let wasLive = false
      let goneStreak = 0
      do {
        if (isGone()) return
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
    }

    if (isGone()) return

    // report (Step 4) — auto-pilot means "auto to report", so the driver
    // kicks report generation after the run. Best-effort: a report failure
    // does not fail the whole pipeline (the run + graph still succeeded).
    {
      store.setStatus(id, 'reporting'); signal()
      // Resume guard: a stored reportId means the report already exists —
      // regenerating with force_regenerate would burn LLM calls and
      // overwrite the finished report on every browser refresh.
      if (!entry.reportId) {
        try {
          const r = (await api.generateReport({ simulation_id: simId, force_regenerate: true })).data || {}
          // keep the report id so an observing page can follow through to it
          if (r.report_id) store.patch(id, { reportId: r.report_id })
        } catch (e) { /* report is best-effort */ }
      }
      store.setStatus(id, 'done'); signal()
    }
  } catch (e) {
    // keep the reason on the entry — the failed card shows it to the user
    store.patch(id, { error: String((e && e.message) || e) })
    store.setStatus(id, 'failed'); signal()
  } finally {
    inFlight.delete(id)
  }
}

// Reconstruct FormData for the ontology call from the (persisted) entry.
// The base64 copy is preferred: it's a plain string, deterministic on every
// retry, and immune to the reactive-proxy/staleness issues a live File object
// routed through the store can hit. Never POST without bytes — the server's
// "please upload a file" 400 would mislead the user about what went wrong.
export function buildFormData(entry) {
  const fd = new FormData()
  const file = entry.fileB64
    ? b64ToFile({ b64: entry.fileB64, name: entry.fileName, type: entry.fileType })
    : entry.file
  if (!file || !file.size || !file.name) {
    throw new Error('上传文件内容已丢失，请删除该卡片后重新提交')
  }
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

  // 跨标签页收养：另一标签页的取消/新提交（含文件字节）通过 storage 事件同步，
  // 取消立即让本页驱动器停手（isGone），新任务的字节让领导标签页能接手驱动
  let ls = null
  try { ls = window.localStorage } catch { /* SSR/隐私模式 */ }
  if (typeof window !== 'undefined' && ls) {
    const { deserialize } = await import('../store/pipelineQueue.js')
    window.addEventListener('storage', (ev) => {
      if (ev.key !== 'mirofish_pipeline_queue' || !ev.newValue) return
      try { store.adoptExternal(deserialize(ev.newValue)) } catch { /* ignore */ }
    })
  }
  // 每个打开的标签页都跑驱动器；没有唯一领导者时，两个标签页会把同一个任务
  // 各推进一遍（双份 ontology/图谱/模拟 = 双倍 LLM 消耗）。租约在 localStorage，
  // 只有持有者推进流水线；其余标签页只同步显示。
  const TAB_ID = Math.random().toString(36).slice(2)

  // Re-entrancy guard: the tick now awaits several calls; without this a slow
  // tick would overlap itself (duplicate writes, stale merges landing late).
  let tickBusy = false
  setInterval(async () => {
    if (tickBusy) return
    tickBusy = true
    try {
      await syncTick({ store, pipeApi, api, toServerEntry })

      // leadership gate: only the lease holder advances (claim now, lead on
      // the NEXT tick so two simultaneous claimants can't both drive)
      if (ls) {
        const lease = evaluateLease(ls.getItem(LOCK_KEY), TAB_ID, Date.now())
        if (lease.shouldClaim) { ls.setItem(LOCK_KEY, leaseValue(TAB_ID, Date.now())); return }
        if (!lease.isLeader) return
        ls.setItem(LOCK_KEY, leaseValue(TAB_ID, Date.now()))   // heartbeat
      }

      // advance (NOT awaited — runOne runs for minutes; awaiting it would
      // hold tickBusy and starve the sync above). Display-only entries have
      // no file bytes in this browser, so they are never driven.
      const active = store.active.value
      if (active && active.mode === 'auto' && !active._displayOnly) {
        runOne(active, deps, _inFlight); return
      }
      if (!active) {
        // 先窥视队首、再决定是否出队：promoteHead 会无条件把队首翻成
        // 'ontology'（活跃态）。手动条目由用户自己的步骤页驱动，驱动器若把它
        // 翻活跃又不推进，它就永远占着槽位（limbo）。只出队 auto 条目。
        const head = store.raw().entries.find(e => !e._displayOnly && e.status === 'queued')
        if (head && head.mode === 'auto') {
          const h = store.promoteHead()
          if (h) runOne({ ...h, status: 'ontology' }, deps, _inFlight)
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
