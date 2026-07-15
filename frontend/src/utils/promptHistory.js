// Prompt-history selection helpers (pure logic, unit-tested via node --test).
// Spec: docs/specs/2026-07-10-prompt-history-reuse-spec.md

// Panel keeps the 20 most recent unique prompts; hidden-list caps at 200.
export const PROMPT_CAP = 20
export const HIDDEN_CAP = 200

/**
 * Build the panel rows from raw history items.
 * Filters empty prompts, excludes locally-hidden ones, dedupes exact texts
 * (keeping the newest occurrence), sorts newest first, caps at PROMPT_CAP.
 *
 * @param {Array<{simulation_requirement?: string, created_at?: string, simulation_id?: string}>} historyItems
 * @param {string[]} hiddenList - prompt texts hidden on this browser
 * @returns {Array<{text: string, date: string, simulationId: string}>}
 */
export function selectPrompts(historyItems, hiddenList) {
  const hidden = new Set((hiddenList || []).map(t => String(t).trim()))
  const byText = new Map()

  for (const it of historyItems || []) {
    const text = String(it?.simulation_requirement || '').trim()
    if (!text || hidden.has(text)) continue
    const createdAt = String(it?.created_at || '')
    const existing = byText.get(text)
    if (!existing || createdAt > existing.createdAt) {
      byText.set(text, { text, createdAt, simulationId: String(it?.simulation_id || '') })
    }
  }

  return [...byText.values()]
    .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
    .slice(0, PROMPT_CAP)
    .map(({ text, createdAt, simulationId }) => ({
      text,
      date: createdAt.slice(0, 10),
      simulationId
    }))
}

/**
 * Append a prompt text to the hidden-list (immutable), deduped, capped at
 * HIDDEN_CAP with oldest entries evicted first.
 *
 * @param {string[]} hiddenList
 * @param {string} text
 * @returns {string[]} new list
 */
export function addHidden(hiddenList, text) {
  const trimmed = String(text || '').trim()
  const base = hiddenList || []
  if (base.includes(trimmed)) return [...base] // already hidden — no-op
  const next = [...base, trimmed]
  return next.slice(Math.max(0, next.length - HIDDEN_CAP))
}
