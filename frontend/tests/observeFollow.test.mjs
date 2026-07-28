import { test } from 'node:test'
import assert from 'node:assert/strict'
import { targetRouteForEntry, observedEntry, shouldFollow } from '../src/utils/observeFollow.js'

test('ontology stage has no page yet', () => {
  assert.equal(targetRouteForEntry({ status: 'ontology' }), null)
})

test('build stage -> graph page', () => {
  const t = targetRouteForEntry({ status: 'building', projectId: 'proj_1' })
  assert.equal(t.name, 'Process')
  assert.equal(t.params.projectId, 'proj_1')
  assert.equal(t.query.observe, '1')          // stays observe-only, never drives
})

test('prepare stage -> simulation page once a sim exists', () => {
  const t = targetRouteForEntry({ status: 'preparing', projectId: 'p', realSimId: 'sim_1' })
  assert.equal(t.name, 'Simulation')
  assert.equal(t.params.simulationId, 'sim_1')
})

test('running stage -> rounds page', () => {
  const t = targetRouteForEntry({ status: 'running', realSimId: 'sim_1' })
  assert.equal(t.name, 'SimulationRun')
})

test('report id wins -> report page', () => {
  const t = targetRouteForEntry({ status: 'reporting', realSimId: 'sim_1', reportId: 'rep_1' })
  assert.equal(t.name, 'Report')
  assert.equal(t.params.reportId, 'rep_1')
})

test('reporting WITHOUT a report id stays on the rounds page (no backwards bounce)', () => {
  const t = targetRouteForEntry({ status: 'reporting', realSimId: 'sim_1' })
  assert.equal(t.name, 'SimulationRun')
  assert.equal(t.params.simulationId, 'sim_1')
})

test('observedEntry matches by sim id, then project id', () => {
  const entries = [
    { _tmpId: 'a', realSimId: 'sim_1', projectId: 'p1' },
    { _tmpId: 'b', realSimId: null, projectId: 'p2' },
  ]
  assert.equal(observedEntry(entries, 'Simulation', { simulationId: 'sim_1' })._tmpId, 'a')
  assert.equal(observedEntry(entries, 'Process', { projectId: 'p2' })._tmpId, 'b')
  assert.equal(observedEntry(entries, 'Process', { projectId: 'new' }), null)   // not yet created
  assert.equal(observedEntry(entries, 'Process', { projectId: 'nope' }), null)
})

test('shouldFollow only when the target differs from the current route', () => {
  const t = { name: 'SimulationRun', params: { simulationId: 'sim_1' }, query: {} }
  assert.equal(shouldFollow(t, 'SimulationRun', { simulationId: 'sim_1' }), false)  // already there
  assert.equal(shouldFollow(t, 'Simulation', { simulationId: 'sim_1' }), true)      // stage advanced
  assert.equal(shouldFollow(t, 'SimulationRun', { simulationId: 'other' }), true)
  assert.equal(shouldFollow(null, 'Process', {}), false)
})
