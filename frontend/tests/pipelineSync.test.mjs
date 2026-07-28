import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  mergeServerEntries, toServerEntry, advanceStatus, serialize, deserialize,
} from '../src/store/pipelineQueue.js'

const local = (over = {}) => ({
  _tmpId: 't1', status: 'building', prompt: 'p', fileName: 'f.docx',
  fileB64: 'AQID', fileType: '', graphId: null, realSimId: null,
  _dirty: false, _rev: 0, _seenOnServer: false, ...over,
})
const srv = (over = {}) => ({
  tmpId: 't1', status: 'running', prompt: 'p', fileName: 'f.docx',
  graphId: 'g1', simId: 'sim_1', updatedAt: new Date().toISOString(), ...over,
})
const q = (entries = [], tombstones = []) => ({ entries, tombstones })

test('B9: union keeps an in-flight local entry the server has not seen', () => {
  const out = mergeServerEntries(q([local()]), [])
  assert.equal(out.entries.length, 1)
})

test('B10: dirty local wins whole (no status/graphId rollback)', () => {
  const l = local({ status: 'creating', graphId: 'g1', _dirty: true })
  const out = mergeServerEntries(q([l]), [srv({ status: 'building', graphId: null })])
  assert.equal(out.entries[0].status, 'creating')
  assert.equal(out.entries[0].graphId, 'g1')          // not lost -> no rebuild
})

test('B11: field-union preserves local-only fields (file bytes)', () => {
  const out = mergeServerEntries(q([local()]), [srv()])
  assert.equal(out.entries[0].fileB64, 'AQID')        // server never stores this
  assert.equal(out.entries[0].status, 'running')      // server wins on its fields
  assert.equal(out.entries[0].realSimId, 'sim_1')     // simId -> realSimId
})

test('server-only entry hydrates as display-only', () => {
  const out = mergeServerEntries(q([]), [srv({ tmpId: 't9' })])
  assert.equal(out.entries[0]._tmpId, 't9')
  assert.equal(out.entries[0]._displayOnly, true)     // no bytes here
})

test('B4: removal only after seen-then-missing', () => {
  assert.equal(mergeServerEntries(q([local()]), []).entries.length, 1)
  const seen = mergeServerEntries(q([local({ _seenOnServer: true })]), [])
  assert.equal(seen.entries.length, 0)
})

test('B13: tombstone suppresses a stale server entry', () => {
  const out = mergeServerEntries(q([], [{ tmpId: 't1', _deleted: true, _ackedAt: null }]), [srv()])
  assert.equal(out.entries.length, 0)
})

test('B14: tombstone clears only after a DELETE ack, in order', () => {
  const tomb = { tmpId: 't1', _deleted: true, _ackedAt: null }
  assert.equal(mergeServerEntries(q([], [tomb]), []).tombstones.length, 1)     // before ack
  const acked = { ...tomb, _ackedAt: Date.now() }
  assert.equal(mergeServerEntries(q([], [acked]), []).tombstones.length, 0)    // after ack
})

test('B15: dirty outranks seen-then-missing', () => {
  const l = local({ _dirty: true, _seenOnServer: true })
  assert.equal(mergeServerEntries(q([l]), []).entries.length, 1)
})

test('tombstone survives an unrelated mutation and a persist round-trip', () => {
  // Decision 1b: reducers must spread ...q, else this tombstone vanishes
  const withTomb = q([local({ _tmpId: 'other' })], [{ tmpId: 't1', _deleted: true, _ackedAt: null }])
  const after = advanceStatus(withTomb, 'other', 'creating')
  assert.equal((after.tombstones || []).length, 1)
  assert.equal(deserialize(serialize(after)).tombstones.length, 1)
})

test('toServerEntry maps names and omits file bytes', () => {
  const s = toServerEntry(local({ realSimId: 'sim_1' }))
  assert.equal(s.tmpId, 't1')
  assert.equal(s.simId, 'sim_1')
  assert.equal(s.fileB64, undefined)
  assert.equal(s.fileType, undefined)
})
