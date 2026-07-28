import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  makeQueue, enqueue, activeEntry, isFull, capacityFull,
  advanceStatus, backfillSimId, cancel, remove, headToPromote,
  mergeForDisplay, reconcileManual, advanceBySimId, ACTIVE_STATUSES,
  serialize, deserialize, pruneFinished,
} from '../src/store/pipelineQueue.js'

test('pruneFinished drops done + failed, keeps active/queued', () => {
  const q = { entries: [
    { _tmpId: 'a', status: 'failed' },
    { _tmpId: 'b', status: 'done' },
    { _tmpId: 'c', status: 'queued' },
    { _tmpId: 'd', status: 'building' },
  ] }
  assert.deepEqual(pruneFinished(q).entries.map(e => e._tmpId), ['c', 'd'])
})

test('mergeForDisplay exposes projectId for routing a generating card', () => {
  const q = { entries: [{ _tmpId: 'x', status: 'building', realSimId: null, projectId: 'proj_1', fileName: 'f', prompt: 'p' }] }
  const card = mergeForDisplay([], q)[0]
  assert.equal(card._projectId, 'proj_1')
  assert.equal(card.simulation_id, null)
})

test('mergeForDisplay hides failed ghosts', () => {
  const q = { entries: [{ _tmpId: 'x', status: 'failed', realSimId: null, fileName: 'f', prompt: 'p' }] }
  assert.equal(mergeForDisplay([], q).length, 0)
})

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

test('mergeForDisplay backfills prompt/file onto a bare server record (no 未命名模拟)', () => {
  // prepare 写入配置前，服务器历史记录没有 simulation_requirement —— 卡片标题
  // 必须回填流水线条目里的提示词与文件名
  let q = makeQueue()
  q = enqueue(q, { ...sub('a'), prompt: '奶粉舆情模拟', fileName: 'seed.md' })
  q = backfillSimId(q, 'a', 'sim_1')
  const merged = mergeForDisplay([{ simulation_id: 'sim_1', simulation_requirement: '', files: [] }], q)
  assert.equal(merged.length, 1)
  assert.equal(merged[0].simulation_requirement, '奶粉舆情模拟')
  assert.deepEqual(merged[0].files, [{ filename: 'seed.md' }])
})

test('mergeForDisplay keeps server prompt/files when server has them', () => {
  let q = makeQueue()
  q = enqueue(q, { ...sub('a'), prompt: 'local prompt', fileName: 'local.md' })
  q = backfillSimId(q, 'a', 'sim_1')
  const rec = { simulation_id: 'sim_1', simulation_requirement: 'server prompt', files: [{ filename: 'server.md' }] }
  const merged = mergeForDisplay([rec], q)
  assert.equal(merged[0].simulation_requirement, 'server prompt')
  assert.deepEqual(merged[0].files, [{ filename: 'server.md' }])
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
