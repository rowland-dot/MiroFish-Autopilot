import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readCollapsed, writeCollapsed, BANNER_KEY } from '../src/utils/bannerPref.js'

const fake = (init = {}) => {
  const m = { ...init }
  return { getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v) }, _m: m }
}

test('defaults to expanded for a first-time visitor', () => {
  assert.equal(readCollapsed(fake()), false)
})

test('remembers a collapsed choice across visits', () => {
  const s = fake()
  writeCollapsed(s, true)
  assert.equal(s._m[BANNER_KEY], '1')
  assert.equal(readCollapsed(s), true)
})

test('remembers re-expanding', () => {
  const s = fake({ [BANNER_KEY]: '1' })
  writeCollapsed(s, false)
  assert.equal(readCollapsed(s), false)
})

test('never throws when storage is unavailable (private mode)', () => {
  const boom = { getItem() { throw new Error('denied') }, setItem() { throw new Error('denied') } }
  assert.equal(readCollapsed(boom), false)
  assert.doesNotThrow(() => writeCollapsed(boom, true))
})

test('ignores garbage values, treating them as expanded', () => {
  assert.equal(readCollapsed(fake({ [BANNER_KEY]: 'yes' })), false)
})
