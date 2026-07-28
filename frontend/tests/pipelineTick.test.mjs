import { test } from 'node:test'
import assert from 'node:assert/strict'
import { syncTick } from '../src/services/pipelineDriver.js'

const fakeStore = (over = {}) => ({
  calls: [],
  applyServerMerge(e) { this.calls.push(['merge', e]) },
  reconcileManual() { this.calls.push(['reconcile']) },
  prune() { this.calls.push(['prune']) },
  dirtyEntries() { return over.dirty || [] },
  pendingTombstones() { return over.tombs || [] },
  markClean(id) { this.calls.push(['clean', id]) },
  ackTombstone(id) { this.calls.push(['ack', id]) },
  ...over,
})

const okApi = { getSystemStatus: async () => ({ data: {} }) }

test('tick order: merge -> reconcile -> prune -> push dirty', async () => {
  const store = fakeStore({ dirty: [{ _tmpId: 'a', _rev: 1 }] })
  const pipeApi = {
    getPipeline: async () => ({ data: { entries: [] } }),
    putPipelineEntry: async () => { store.calls.push(['put']) },
    deletePipelineEntry: async () => {},
  }
  await syncTick({ store, pipeApi, api: okApi, toServerEntry: (e) => e })
  const seq = store.calls.map(c => c[0])
  assert.deepEqual(seq.slice(0, 3), ['merge', 'reconcile', 'prune'])
  assert.ok(seq.indexOf('put') > seq.indexOf('prune'))   // dirty push AFTER prune
})

test('dirty entry is pushed then marked clean with its rev', async () => {
  const store = fakeStore({ dirty: [{ _tmpId: 'a', _rev: 7 }] })
  const pipeApi = {
    getPipeline: async () => ({ data: { entries: [] } }),
    putPipelineEntry: async () => {},
    deletePipelineEntry: async () => {},
  }
  await syncTick({ store, pipeApi, api: okApi, toServerEntry: (e) => e })
  assert.ok(store.calls.some(c => c[0] === 'clean' && c[1] === 'a'))
})

test('tombstone DELETE is retried and acked', async () => {
  const store = fakeStore({ tombs: [{ tmpId: 'x', _ackedAt: null }] })
  const pipeApi = {
    getPipeline: async () => ({ data: { entries: [] } }),
    putPipelineEntry: async () => {},
    deletePipelineEntry: async () => {},
  }
  await syncTick({ store, pipeApi, api: okApi, toServerEntry: (e) => e })
  assert.ok(store.calls.some(c => c[0] === 'ack' && c[1] === 'x'))
})

test('a failed GET does not abort the rest of the tick', async () => {
  const store = fakeStore({ dirty: [{ _tmpId: 'a', _rev: 1 }] })
  const pipeApi = {
    getPipeline: async () => { throw new Error('offline') },
    putPipelineEntry: async () => { store.calls.push(['put']) },
    deletePipelineEntry: async () => {},
  }
  await syncTick({ store, pipeApi, api: okApi, toServerEntry: (e) => e })
  assert.ok(store.calls.some(c => c[0] === 'put'))       // still pushed
})

test('a failed PUT does not mark the entry clean (retried next tick)', async () => {
  const store = fakeStore({ dirty: [{ _tmpId: 'a', _rev: 1 }] })
  const pipeApi = {
    getPipeline: async () => ({ data: { entries: [] } }),
    putPipelineEntry: async () => { throw new Error('offline') },
    deletePipelineEntry: async () => {},
  }
  await syncTick({ store, pipeApi, api: okApi, toServerEntry: (e) => e })
  assert.ok(!store.calls.some(c => c[0] === 'clean'))
})
