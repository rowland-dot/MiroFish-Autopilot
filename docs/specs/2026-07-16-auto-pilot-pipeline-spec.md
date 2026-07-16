# Auto-Pilot Pipeline (continuous run) — lite spec

## Purpose
One click on the landing page runs the whole pipeline unattended —
graph build → env setup → simulation → report — instead of manually clicking
"next" at the end of every step. The existing manual flow stays the default.

## Background (verified flow map)
Each step's *work* already auto-starts on arrival; only the four step-to-step
transitions are manual clicks. Auto-pilot therefore only automates those four
transitions by invoking the existing handlers when each step's existing
completion flag flips:

| From → To | Completion flag | Existing handler invoked |
|---|---|---|
| 1 Graph → 2 Env | `currentPhase === 2` (MainView) | `handleEnterEnvSetup` (Step1GraphBuild) |
| 2 Env → 3 Sim | `phase === 4` (Step2EnvSetup) | `handleStartSimulation` (Step2EnvSetup) |
| 3 Sim → 4 Report | `phase === 2` (Step3Simulation) | `handleNextStep` (Step3Simulation) |
| 4 Report → 5 Interact | `isComplete` (Step4Report) | `goToInteraction` (Step4Report) |

## Behaviors (entry → action → result)
1. **Launch (manual, unchanged).** Entry: landing page, file + prompt present.
   Action: click `启动引擎 →`. Result: exactly today's flow.
2. **Launch (auto).** Action: click `⚡ 自动直达报告` (subtitle: 全程无人值守 ·
   1→5 步自动推进). Result: auto-pilot flag set, then the same launch as (1).
   Both buttons share the same enable-rule (`canSubmit`).
3. **Auto-advance.** Entry: any step completes while the flag is on. Result:
   after a ~1.5 s pause (user sees the completed state), the step's existing
   "next" handler fires. Existing disabled-guards make this idempotent.
4. **Mid-flight indicator.** While the flag is on, every step header shows an
   `⚡ AUTO-PILOT · 退出自动` pill.
5. **Exit.** Action: click 退出自动. Result: flag cleared; current step
   continues normally in manual mode; nothing is cancelled.
6. **Failure = safe stop.** A step that errors never reaches its completion
   flag, so auto-advance simply never fires; normal error UI applies. No
   automatic retries (protects API spend).
7. **Terminal.** Arriving at Step 5 (Interaction) clears the flag.

## Decisions defaulted in auto mode
- Simulation rounds: auto-planned config (no custom cap) — the same default
  as clicking through manually without touching the toggle.
- Platforms: both on (already hardcoded in the Step 1 handler).
- Report: auto-generated (Step 3's existing handler does this).

## Constraints / honest caveats
- Transitions run in the browser: the tab must stay open. Server-side work in
  the current step continues regardless; closing the tab mid-run means
  resuming manually (flag is per-tab).
- One click spends a full pipeline's tokens without a human checkpoint — the
  button subtitle says so.

## Implementation shape
- `frontend/src/utils/autoPilot.js` — tiny module over sessionStorage:
  `isAutoPilot()`, `enableAutoPilot()`, `disableAutoPilot()`. Pure,
  unit-tested via `node --test` (storage injectable for tests).
- `Home.vue` — split the launch button into the two buttons + hint line;
  auto button calls `enableAutoPilot()` then the existing `startSimulation()`.
- Four watchers (MainView/Step1, Step2EnvSetup, Step3Simulation, Step4Report):
  when completion flag flips and `isAutoPilot()`, `setTimeout` ~1.5 s → call
  the existing handler. Step 5 view clears the flag on mount.
- Auto-pilot pill: small shared component `AutoPilotPill.vue` rendered in each
  step view's header while active.
- Locale strings EN/ZH for: auto button title/subtitle, hint line, pill label,
  exit, "next up" strip.

## Testing
- `node --test`: autoPilot module (enable/disable/persistence semantics,
  injectable storage; default off; clear on terminal).
- Browser-verify: split buttons render + enable-rule; full auto run
  chains 1→5 hands-free; exit pill stops advancing; error stop (simulated by
  killing the backend mid-step) leaves manual controls usable.

## Out of scope
- Server-side orchestration (survives tab close) — future work if HF usage
  demands it.
- Auto-retry on failures.
- Per-step notification emails/pings.
