// Cross-tab driver leadership. Every open tab mounts the app-level driver;
// without a single leader, two tabs both promote and drive the same entry —
// duplicate ontology/graph/simulation/prepare/report calls, i.e. double LLM
// cost per job (the ghost-job class of incidents). Only the lease holder
// advances the pipeline; all tabs still sync for display.
//
// Pure functions — the driver injects real localStorage + Date.now().

export const LOCK_KEY = 'mirofish_driver_leader'
export const LEASE_TTL_MS = 10000

// Decide this tab's role from the stored lease.
// - absent / corrupt / stale lease: not leader yet, but should claim it.
//   (Claim-then-lead-NEXT-tick: two tabs claiming simultaneously overwrite
//   each other; whoever's write survives is confirmed a tick later.)
// - fresh lease: leader iff it is ours.
export function evaluateLease(raw, tabId, now, ttlMs = LEASE_TTL_MS) {
  let lock = null
  try { lock = JSON.parse(raw) } catch { /* corrupt = absent */ }
  if (!lock || typeof lock.ts !== 'number' || now - lock.ts > ttlMs) {
    return { isLeader: false, shouldClaim: true }
  }
  return { isLeader: lock.id === tabId, shouldClaim: false }
}

export function leaseValue(tabId, now) {
  return JSON.stringify({ id: tabId, ts: now })
}
