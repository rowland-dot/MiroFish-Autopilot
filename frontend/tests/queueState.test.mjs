import { test } from 'node:test'
import assert from 'node:assert/strict'
import { isQueued, queuePosition } from '../src/utils/queueState.js'

test('isQueued true when id in list', () => {
  assert.equal(isQueued('sim_a', ['sim_a', 'sim_b']), true)
})

test('isQueued false when id not in list', () => {
  assert.equal(isQueued('sim_z', ['sim_a', 'sim_b']), false)
})

test('isQueued false on bad input', () => {
  assert.equal(isQueued('sim_a', null), false)
  assert.equal(isQueued(null, ['sim_a']), false)
})

test('queuePosition is 1-based, 0 when absent', () => {
  assert.equal(queuePosition('sim_a', ['sim_a', 'sim_b']), 1)
  assert.equal(queuePosition('sim_b', ['sim_a', 'sim_b']), 2)
  assert.equal(queuePosition('sim_z', ['sim_a', 'sim_b']), 0)
})
