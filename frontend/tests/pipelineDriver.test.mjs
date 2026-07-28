import { test } from 'node:test'
import assert from 'node:assert/strict'
import { runOne } from '../src/services/pipelineDriver.js'

function mockApi(calls) {
  return {
    generateOntology: async () => (calls.push('ontology'), { data: { project_id: 'proj_1' } }),
    buildGraph: async () => (calls.push('build'), { data: { reused: true, graph_id: 'g1' } }),
    getTaskStatus: async () => ({ data: { status: 'completed' } }),
    getProject: async () => ({ data: { graph_id: 'g1' } }),
    createSimulation: async () => (calls.push('create'), { data: { simulation_id: 'sim_1' } }),
    prepareSimulation: async () => (calls.push('prepare'), { data: { task_id: 'pt1' } }),
    getPrepareStatus: async () => ({ data: { status: 'completed' } }),
    startSimulation: async () => (calls.push('start'), { data: { runner_status: 'running' } }),
    // realistic: the run is live for a poll, then finishes
    getRunStatus: (() => { let n = 0; return async () => ({ data: { runner_status: n++ === 0 ? 'running' : 'completed' } }) })(),
    getSystemStatus: async () => ({ data: { running_simulations: ['sim_1'] } }),
    generateReport: async () => (calls.push('report'), { data: { report_id: 'rep_1' } }),
  }
}
// non-reused build path: buildGraph returns a task -> poll -> getProject
function mockApiPolling(calls) {
  return { ...mockApi(calls),
    buildGraph: async () => (calls.push('build'), { data: { task_id: 'bt1' } }) }
}

function deps(api) {
  const rec = { sid: null, statuses: [] }
  return {
    api,
    store: { setStatus(_id, s) { rec.statuses.push(s) }, setSimId(_id, sid) { rec.sid = sid }, patch() {} },
    sleep: async () => {}, signal: () => {}, buildFormData: () => ({}),
    _rec: rec,
  }
}

test('runOne advances through the full sequence and backfills sim id', async () => {
  const calls = []
  const d = deps(mockApi(calls))
  await runOne({ _tmpId: 't1', file: {}, prompt: 'p' }, d)
  assert.deepEqual(calls, ['ontology', 'build', 'create', 'prepare', 'start', 'report'])
  assert.equal(d._rec.sid, 'sim_1')                                  // backfilled
  assert.deepEqual(d._rec.statuses, ['building', 'creating', 'preparing', 'running', 'reporting', 'done'])
  // 'running' must come AFTER the start call — marking it earlier let the
  // server-side reconcile delete the card mid-pipeline.
  assert.ok(d._rec.statuses.indexOf('running') > 0)
})

test('runOne polls the non-reused build task + prepare task', async () => {
  const calls = []
  await runOne({ _tmpId: 't2', file: {}, prompt: 'p' }, deps(mockApiPolling(calls)))
  assert.deepEqual(calls, ['ontology', 'build', 'create', 'prepare', 'start', 'report'])
})

test('a second tick does not re-enter runOne for an in-flight entry', async () => {
  const calls = []
  const api = mockApi(calls)
  let resolveOnto
  api.generateOntology = () => new Promise(r => { calls.push('ontology'); resolveOnto = () => r({ data: { project_id: 'proj_1' } }) })
  const inFlight = new Set()
  const entry = { _tmpId: 't3', mode: 'auto', file: {}, prompt: 'p' }
  const d = deps(api)
  const p1 = runOne(entry, d, inFlight)   // enters, adds t3, awaits ontology
  const p2 = runOne(entry, d, inFlight)   // must no-op (t3 already in flight)
  resolveOnto()
  await Promise.all([p1, p2])
  assert.equal(calls.filter(c => c === 'ontology').length, 1)
})

test('runOne resumes from create when graphId already present (no rebuild)', async () => {
  const calls = []
  await runOne({ _tmpId: 't4', file: {}, prompt: 'p', projectId: 'proj_1', graphId: 'g1' }, deps(mockApi(calls)))
  assert.deepEqual(calls, ['create', 'prepare', 'start', 'report'])   // skipped ontology + build
})
