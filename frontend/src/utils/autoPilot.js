// Auto-pilot flag: when on, each pipeline step auto-advances to the next on
// completion. Persisted in sessionStorage so it survives the router.push page
// transitions between step views (per-tab; cleared on tab close).
// Spec: docs/specs/2026-07-16-auto-pilot-pipeline-spec.md

export const AUTO_PILOT_KEY = 'mirofish_auto_pilot'
const ON = '1'

/**
 * Factory over an injectable Storage (tests pass a stub; app uses
 * sessionStorage). All operations degrade silently to "off" when storage is
 * unavailable (e.g. blocked in private mode).
 */
export function createAutoPilot(storage) {
  const safe = (fn, fallback) => {
    try { return fn() } catch { return fallback }
  }
  return {
    isAutoPilot: () => safe(() => storage.getItem(AUTO_PILOT_KEY) === ON, false),
    enableAutoPilot: () => { safe(() => storage.setItem(AUTO_PILOT_KEY, ON)) },
    disableAutoPilot: () => { safe(() => storage.removeItem(AUTO_PILOT_KEY)) }
  }
}

// App-wide instance bound to the browser's sessionStorage.
const app = createAutoPilot(typeof sessionStorage !== 'undefined' ? sessionStorage : null)
export const isAutoPilot = app.isAutoPilot
export const enableAutoPilot = app.enableAutoPilot
export const disableAutoPilot = app.disableAutoPilot
