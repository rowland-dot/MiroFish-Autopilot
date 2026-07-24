// Queue-state helpers. A simulation is "queued" iff its id is in the
// server's queued list (from /api/status) — NOT inferred from round count,
// because a queued sim has current_round=0 and would look like a
// never-started one. Spec: 2026-07-25-simulation-queue-spec.md B6.

export function isQueued(simulationId, queuedIds) {
  if (!simulationId || !Array.isArray(queuedIds)) return false
  return queuedIds.includes(simulationId)
}

// Queue position (1-based) for display, or 0 if not queued.
export function queuePosition(simulationId, queuedIds) {
  if (!Array.isArray(queuedIds)) return 0
  const i = queuedIds.indexOf(simulationId)
  return i < 0 ? 0 : i + 1
}
