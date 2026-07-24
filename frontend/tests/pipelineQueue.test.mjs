import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  makeQueue, enqueue, activeEntry, isFull, capacityFull,
  advanceStatus, backfillSimId, cancel, remove, headToPromote,
  mergeForDisplay, reconcileManual, advanceBySimId, ACTIVE_STATUSES,
  serialize, deserialize,
} from '../src/store/pipelineQueue.js'

const sub = (id, over = {}) => ({ _tmpId: id, prompt: 'p', fileName: 'x.docx', status: 'queued', realSimId: null, ...over })

test('enqueue respects slot=1 + queue=2 (capacity 3)', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  assert.equal(q.entries[0].status, 'ontology')
  q = enqueue(q, sub('b'))
  q = enqueue(q, sub('c'))
  assert.equal(capacityFull(q), true)
  q = enqueue(q, sub('d'))
  assert.equal(q.entries.length, 3)
})

test('only one active at a time', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = enqueue(q, sub('b'))
  assert.equal(q.entries.filter(e => ACTIVE_STATUSES.includes(e.status)).length, 1)
  assert.equal(activeEntry(q)._tmpId, 'a')
})

test('advanceStatus moves the active entry forward', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = advanceStatus(q, 'a', 'building')
  assert.equal(q.entries[0].status, 'building')
})

test('backfillSimId writes realSimId on the entry', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = backfillSimId(q, 'a', 'sim_123')
  assert.equal(q.entries[0].realSimId, 'sim_123')
})

test('headToPromote returns oldest queued when no active', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = enqueue(q, sub('b'))
  q = advanceStatus(q, 'a', 'done')
  const head = headToPromote(q)
  assert.equal(head._tmpId, 'b')
  assert.equal(headToPromote(makeQueue()), null)
})

test('headToPromote is null while something is active', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = enqueue(q, sub('b'))
  assert.equal(headToPromote(q), null)
})

test('cancel / remove drop a queued entry', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = enqueue(q, sub('b'))
  q = cancel(q, 'b')
  assert.deepEqual(q.entries.map(e => e._tmpId), ['a'])
})

test('mergeForDisplay suppresses optimistic entry once server has its realSimId', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  q = backfillSimId(q, 'a', 'sim_1')
  const serverList = [{ simulation_id: 'sim_1', foo: 1 }]
  const merged = mergeForDisplay(serverList, q)
  assert.equal(merged.length, 1)
  assert.equal(merged[0].simulation_id, 'sim_1')
})

test('mergeForDisplay keeps optimistic entry not yet in server list', () => {
  let q = makeQueue()
  q = enqueue(q, sub('a'))
  const merged = mergeForDisplay([], q)
  assert.equal(merged.length, 1)
  assert.equal(merged[0]._tmpId, 'a')
  assert.equal(merged[0]._optimistic, true)
})

test('advanceBySimId sets status on the entry matching realSimId', () => {
  let q = makeQueue()
  q = enqueue(q, sub('m', { mode: 'manual' }))
  q = backfillSimId(q, 'm', 'sim_x')
  q = advanceBySimId(q, 'sim_x', 'done')
  assert.equal(q.entries[0].status, 'done')
  // no-op when no match
  assert.equal(advanceBySimId(q, 'nope', 'running').entries[0].status, 'done')
})

test('serialize/deserialize round-trips through a storage string', () => {
  let q = makeQueue()
  q = enqueue(q, { _tmpId: 'a', prompt: 'p', fileB64: 'AQID', fileName: 'x.docx', fileType: '', realSimId: null })
  const json = serialize(q)
  const back = deserialize(json)
  assert.equal(back.entries[0]._tmpId, 'a')
  assert.equal(back.entries[0].fileB64, 'AQID')
  assert.equal(back.entries[0].status, 'ontology')
})

test('deserialize tolerates garbage', () => {
  assert.deepEqual(deserialize('not json').entries, [])
})

test('reconcileManual marks a finished manual entry done', () => {
  let q = makeQueue()
  q = enqueue(q, sub('m', { mode: 'manual' }))
  q = advanceStatus(q, 'm', 'running')
  q = backfillSimId(q, 'm', 'sim_m')
  assert.equal(reconcileManual(q, []).entries[0].status, 'done')
  assert.equal(reconcileManual(q, ['sim_m']).entries[0].status, 'running')
})
