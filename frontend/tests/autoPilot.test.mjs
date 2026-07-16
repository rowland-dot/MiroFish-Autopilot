// TDD: auto-pilot flag module (run: node --test frontend/tests)
// Spec: docs/specs/2026-07-16-auto-pilot-pipeline-spec.md
import { test } from 'node:test'
import assert from 'node:assert/strict'

import { createAutoPilot, AUTO_PILOT_KEY } from '../src/utils/autoPilot.js'

// Minimal sessionStorage stand-in
const memStorage = () => {
  const m = new Map()
  return {
    getItem: k => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: k => m.delete(k)
  }
}

test('off by default', () => {
  const ap = createAutoPilot(memStorage())
  assert.equal(ap.isAutoPilot(), false)
})

test('enable turns it on and persists to storage', () => {
  const store = memStorage()
  const ap = createAutoPilot(store)
  ap.enableAutoPilot()
  assert.equal(ap.isAutoPilot(), true)
  // a fresh instance over the same storage sees it (route navigation survives)
  assert.equal(createAutoPilot(store).isAutoPilot(), true)
})

test('disable turns it off and clears storage', () => {
  const store = memStorage()
  const ap = createAutoPilot(store)
  ap.enableAutoPilot()
  ap.disableAutoPilot()
  assert.equal(ap.isAutoPilot(), false)
  assert.equal(store.getItem(AUTO_PILOT_KEY), null)
  assert.equal(createAutoPilot(store).isAutoPilot(), false)
})

test('survives storage that throws (private mode) by degrading to off', () => {
  const broken = {
    getItem: () => { throw new Error('denied') },
    setItem: () => { throw new Error('denied') },
    removeItem: () => { throw new Error('denied') }
  }
  const ap = createAutoPilot(broken)
  assert.equal(ap.isAutoPilot(), false)      // read failure -> off
  assert.doesNotThrow(() => ap.enableAutoPilot())
  assert.doesNotThrow(() => ap.disableAutoPilot())
})

test('only the exact sentinel value counts as on', () => {
  const store = memStorage()
  store.setItem(AUTO_PILOT_KEY, 'garbage')
  assert.equal(createAutoPilot(store).isAutoPilot(), false)
})
