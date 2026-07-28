import { test } from 'node:test'
import assert from 'node:assert/strict'
import { pipelineStore } from '../src/store/pipelineQueue.js'

const reset = () => pipelineStore.reset()

test('add seeds _rev and marks dirty', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', prompt: 'p', fileName: 'f', fileB64: 'AQID' })
  const e = pipelineStore.entries.value[0]
  assert.equal(e._rev, 0)
  assert.equal(e._dirty, true)
  assert.deepEqual(pipelineStore.dirtyEntries().map(x => x._tmpId), ['a'])
})

test('markClean clears dirty only if _rev is unchanged', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', prompt: 'p' })
  const rev = pipelineStore.entries.value[0]._rev
  pipelineStore.setStatus('a', 'building')            // bumps _rev
  pipelineStore.markClean('a', rev)                   // stale ack -> ignored
  assert.equal(pipelineStore.entries.value[0]._dirty, true)
  pipelineStore.markClean('a', pipelineStore.entries.value[0]._rev)
  assert.equal(pipelineStore.entries.value[0]._dirty, false)
})

test('cancel removes locally and leaves a tombstone', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', prompt: 'p' })
  pipelineStore.cancel('a')
  assert.equal(pipelineStore.entries.value.length, 0)
  assert.deepEqual(pipelineStore.pendingTombstones().map(t => t.tmpId), ['a'])
})

test('prune tombstones what it drops (so the server converges)', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', prompt: 'p' })
  pipelineStore.setStatus('a', 'done')
  pipelineStore.prune()
  assert.equal(pipelineStore.entries.value.length, 0)
  assert.deepEqual(pipelineStore.pendingTombstones().map(t => t.tmpId), ['a'])
})

test('applyServerMerge writes back entries AND tombstones', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', prompt: 'p' })
  pipelineStore.cancel('a')                           // tombstone for 'a'
  pipelineStore.applyServerMerge([{ tmpId: 'a', status: 'queued', updatedAt: new Date().toISOString() }])
  assert.equal(pipelineStore.entries.value.length, 0)         // suppressed
  assert.equal(pipelineStore.pendingTombstones().length, 1)   // retained for retry
})

test('ackTombstone stamps _ackedAt and stops the retry', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', prompt: 'p' })
  pipelineStore.cancel('a')
  pipelineStore.ackTombstone('a')
  assert.equal(pipelineStore.pendingTombstones().length, 0)   // acked -> not retried
  assert.ok(pipelineStore.tombstones()[0]._ackedAt)           // but still suppressing
})

test('B16: a display-only entry does not hold the slot', () => {
  reset()
  pipelineStore.applyServerMerge([{ tmpId: 'other', status: 'building', updatedAt: new Date().toISOString() }])
  assert.equal(pipelineStore.entries.value[0]._displayOnly, true)
  assert.equal(pipelineStore.active.value, null)              // does NOT occupy the slot
  pipelineStore.add({ _tmpId: 'mine', prompt: 'p', fileB64: 'AQID' })
  assert.equal(pipelineStore.active.value._tmpId, 'mine')     // this browser can still run
})

test('B16b: display-only queued entries do not block submitting', () => {
  reset()
  const now = new Date().toISOString()
  pipelineStore.applyServerMerge([
    { tmpId: 'x1', status: 'queued', updatedAt: now },
    { tmpId: 'x2', status: 'queued', updatedAt: now },
    { tmpId: 'x3', status: 'building', updatedAt: now },
  ])
  assert.equal(pipelineStore.capacityFull.value, false)       // other browser's entries don't gate me
})

test('setStatusBySimId marks dirty (manual runs must sync their done)', () => {
  reset()
  pipelineStore.add({ _tmpId: 'a', mode: 'manual', prompt: 'p' })
  pipelineStore.setSimId('a', 'sim_1')
  pipelineStore.markClean('a', pipelineStore.entries.value[0]._rev)
  pipelineStore.setStatusBySimId('sim_1', 'done')
  assert.equal(pipelineStore.entries.value[0]._dirty, true)
})
