# Prompt History (fast reuse) — lite spec

## Purpose
Let users refill the landing-page prompt box from previously used prompts in
one click, instead of retyping long simulation requirements.

## Data source (no new storage)
Prompts come from the existing `GET /api/simulation/history` endpoint, which
already returns `simulation_requirement` per past run. The feature is
**frontend-only**: fetch up to 50 recent runs, drop empty prompts, dedupe
exact-duplicate texts (keep newest), drop locally-hidden ones, keep the
**20 most recent unique** prompts.

## Behaviors (entry → action → result)
1. **History button.** Entry: landing page, ≥1 usable past prompt exists.
   Result: a `↺ History (N)` button renders on the prompt header row
   (next to "02 / 模拟提示词"). With zero usable prompts the button does not
   render at all.
2. **Open panel.** Action: click the button. Result: a **floating overlay
   panel** drops over the textarea — the page layout never moves or resizes.
   Header: `RECENT PROMPTS · N`, a **Clear all** link, and ✕. List: up to 20
   rows (2-line clamped text + date + short sim id), a few visible, then
   scrolls. Footer notes the scroll/cap.
3. **Reuse a prompt.** Action: click a row. Result: its full text replaces the
   textarea content; the panel closes; nothing auto-submits — the user can
   edit before launching.
4. **Hide one prompt.** Action: hover a row → click its ✕. Result: the row
   disappears and that prompt text is never suggested again on this browser.
5. **Clear all.** Action: click **Clear all**. Result: all currently listed
   prompts are hidden (per-browser); the panel shows empty and the button
   disappears until new prompts are used.
6. **Dismiss.** Action: click ✕ in the header or anywhere outside the panel.
   Result: panel closes, textarea untouched.

## Management model
- Hiding is a **per-browser preference** (localStorage list of hidden prompt
  texts, capped at 200 entries, oldest evicted). It never deletes projects or
  affects teammates on the shared deploy.
- The prompt *data* remains server-derived; no cap to manage server-side —
  older prompts naturally fall out of the newest-50 window.

## Implementation shape
- `frontend/src/utils/promptHistory.js` — pure helpers:
  `selectPrompts(historyItems, hiddenList)` (filter → dedupe → sort → cap 20)
  and `addHidden(hiddenList, text)` (append + cap 200). Unit-testable logic
  isolated from the UI.
- `Home.vue` — button + overlay panel (per the approved mockup), wired to the
  history data already fetched for the landing page, plus the localStorage
  hidden-list.
- Locale strings added to `locales/en.json` + `locales/zh.json`.

## Testing
- Pure-helper tests (dedupe keeps newest; empty prompts dropped; hidden
  excluded; cap 20; hidden-list cap 200). MiroFish has no frontend test
  runner, so helpers are covered by a minimal node test script run in CI/dev;
  the UI states are browser-verified against the approved mockup.

## Out of scope
- Search/filter within the panel (revisit if history outgrows 20).
- Server-side prompt favourites/pinning.
- Cross-browser sync of hidden preferences.
