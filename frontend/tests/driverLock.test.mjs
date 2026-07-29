import { test } from 'node:test'
import assert from 'node:assert/strict'
import { evaluateLease, leaseValue } from '../src/services/driverLock.js'

test('absent or corrupt lease: claim, but do not lead this tick', () => {
  for (const raw of [null, '', 'garbage', '{}']) {
    const r = evaluateLease(raw, 'tabA', 1000)
    assert.deepEqual(r, { isLeader: false, shouldClaim: true }, String(raw))
  }
})

test('own fresh lease: leader', () => {
  const r = evaluateLease(leaseValue('tabA', 1000), 'tabA', 5000)
  assert.deepEqual(r, { isLeader: true, shouldClaim: false })
})

test('another tab holds a fresh lease: not leader, no claim', () => {
  const r = evaluateLease(leaseValue('tabB', 1000), 'tabA', 5000)
  assert.deepEqual(r, { isLeader: false, shouldClaim: false })
})

test('stale lease from a dead tab: claimable', () => {
  const r = evaluateLease(leaseValue('tabB', 1000), 'tabA', 20001)
  assert.deepEqual(r, { isLeader: false, shouldClaim: true })
})
