// Hero-banner fold preference. Remembered across visits so the working
// dashboard is the first thing on screen for returning users, instead of a
// tall intro banner they scroll past every time.
//
// Pure read/write helpers (storage injected) so they are unit-testable and
// the caller can read the value BEFORE first paint — no expand-then-collapse
// flash on load.

export const BANNER_KEY = 'mirofish_banner_collapsed'

// Default is EXPANDED: a first-time visitor should see the intro.
export function readCollapsed(storage) {
  try { return storage.getItem(BANNER_KEY) === '1' } catch { return false }
}

export function writeCollapsed(storage, collapsed) {
  try { storage.setItem(BANNER_KEY, collapsed ? '1' : '0') } catch { /* private mode: session-only */ }
}
