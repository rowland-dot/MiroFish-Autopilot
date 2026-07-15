// TDD: prompt-history selection helpers (run: node --test frontend/tests)
// Pure logic behind the landing-page History panel — spec:
// docs/specs/2026-07-10-prompt-history-reuse-spec.md
import { test } from 'node:test'
import assert from 'node:assert/strict'

import { selectPrompts, addHidden, HIDDEN_CAP, PROMPT_CAP } from '../src/utils/promptHistory.js'

const item = (text, created_at, simulation_id = 'sim_x') => ({
  simulation_requirement: text,
  created_at,
  simulation_id
})

test('newest first, empty prompts dropped', () => {
  const out = selectPrompts(
    [item('old', '2026-07-01'), item('', '2026-07-09'), item('new', '2026-07-08'), item(null, '2026-07-07')],
    []
  )
  assert.deepEqual(out.map(p => p.text), ['new', 'old'])
})

test('exact duplicates deduped keeping the newest occurrence', () => {
  const out = selectPrompts(
    [item('same', '2026-07-01', 'sim_old'), item('same', '2026-07-09', 'sim_new'), item('other', '2026-07-05')],
    []
  )
  assert.equal(out.length, 2)
  assert.equal(out[0].text, 'same')
  assert.equal(out[0].simulationId, 'sim_new') // newest occurrence wins
})

test('hidden prompts are excluded', () => {
  const out = selectPrompts([item('keep', '2026-07-09'), item('hideme', '2026-07-08')], ['hideme'])
  assert.deepEqual(out.map(p => p.text), ['keep'])
})

test('whitespace-only prompts dropped and text trimmed before matching', () => {
  const out = selectPrompts([item('   ', '2026-07-09'), item('  padded  ', '2026-07-08')], ['padded'])
  assert.equal(out.length, 0) // trimmed text matches hidden entry
})

test(`caps at ${PROMPT_CAP} prompts`, () => {
  const items = Array.from({ length: 30 }, (_, i) =>
    item(`prompt ${i}`, `2026-06-${String(i + 1).padStart(2, '0')}`)
  )
  const out = selectPrompts(items, [])
  assert.equal(out.length, PROMPT_CAP)
  assert.equal(out[0].text, 'prompt 29') // newest kept
})

test('addHidden appends, dedupes, and evicts oldest past the cap', () => {
  assert.deepEqual(addHidden(['a'], 'b'), ['a', 'b'])
  assert.deepEqual(addHidden(['a', 'b'], 'a'), ['a', 'b']) // no dupes
  const full = Array.from({ length: HIDDEN_CAP }, (_, i) => `h${i}`)
  const out = addHidden(full, 'newest')
  assert.equal(out.length, HIDDEN_CAP)
  assert.equal(out[out.length - 1], 'newest')
  assert.equal(out.includes('h0'), false) // oldest evicted
})

test('rows expose display fields (date + short sim id)', () => {
  const [row] = selectPrompts([item('hello', '2026-07-09T12:34:56', 'sim_48ac9fe52e7e')], [])
  assert.equal(row.date, '2026-07-09')
  assert.equal(row.simulationId, 'sim_48ac9fe52e7e')
})
