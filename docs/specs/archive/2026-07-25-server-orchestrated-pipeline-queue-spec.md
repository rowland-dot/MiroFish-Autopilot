# Server-Orchestrated Pipeline Queue + 运行中 Badge — Spec

**Date:** 2026-07-25
**Status:** Approved direction (user: ship both, one deploy)
**Supersedes the run-step-only queue** (2026-07-25-simulation-queue-spec.md)
with a submit-time, server-driven pipeline queue.

## Why the previous queue was wrong

The shipped queue only gated `/api/simulation/start` (the OASIS run).
But the heavy work (graph build + prepare) happens BEFORE that, driven
by the frontend across Step pages. And auto-pilot is a browser flag —
navigating away (clicking the logo to start another project) kills the
auto-pilot chain. Result: starting 3 projects, 2 orphan at graph-build
and only 1 survives (confirmed from Space logs 2026-07-24: 3 graph
builds completed, only 1 `create` fired). The queue never engaged
because the orphaned projects never reached the run step.

## Fix: two parts

### Part 1 — 运行中 badge (frontend)

Mirror the existing 排队中 badge. A history card whose `simulation_id`
is in `/api/status` `running_simulations` shows a green **运行中**
corner badge. This closes the gap against the approved mockup (which
showed both 运行中 and 排队中; only 排队中 was shipped).

**B-badge:** entry = home page with a running sim; result = its card
shows a green 运行中 badge top-right, matching the queued badge shape.

### Part 1b — instant history card on click (both auto AND manual)

**B-instant:** entry = home page, file uploaded + prompt entered.
Action = click 启动引擎 (manual) OR 自动直达报告 (auto). Result = a
history card for this project appears **immediately**, before any
navigation or heavy work. The card exists because the submission
creates the record server-side at click time (the sim/project id is
allocated up front). Applies to BOTH start paths — no more "card shows
up minutes later after graph build."

Concretely: both buttons call `POST /api/pipeline/submit`, which
allocates the id + writes the record synchronously and returns it, so
the Home history list (refreshed on submit) shows the card at once —
with 运行中 (if it started) or 排队中 (if queued).

### Part 2 — server-orchestrated pipeline queue

Move the whole auto-pilot pipeline server-side so it survives frontend
navigation, and gate it at SUBMIT time.

#### Pipeline

On submit, the backend runs these steps autonomously with recommended
settings (exactly what auto-pilot does today, but server-driven):

1. Graph build (Zep) — from the uploaded file + prompt
2. Create simulation
3. Prepare (ontology/config/profiles, env setup)
4. Run (OASIS)

A background orchestrator thread owns one pipeline end-to-end. The
frontend only submits and polls status — closing the tab or navigating
away does NOT stop the pipeline.

#### Queue (reuses SimulationQueue: slot=1, queue=2)

The "slot" now means **one active pipeline**, not one OASIS run. A
pipeline occupies the slot for its whole life (graph → run → report).

- **B1 — idle submit runs now.** No active pipeline → submit starts the
  pipeline immediately; its card shows 运行中 (once it reaches a
  running-tracked step) / a pipeline-active indicator.
- **B2 — submit while active enqueues.** One pipeline active, queue
  < 2 → the submission is queued (payload = the file + prompt +
  recommended settings). No graph build starts yet. Card shows 排队中.
- **B3 — full disables submit.** 1 active + 2 queued → the start
  section (both buttons) is disabled with `队列已满` hint.
- **B4 — auto-promote on pipeline completion.** When the active
  pipeline finishes (report produced, or failed/cancelled), the oldest
  queued submission's pipeline starts automatically (option A: whole
  pipeline, not just the run).
- **B5 — cancel queued.** 取消排队 removes a queued submission before
  its pipeline starts (nothing built yet; just drop the payload).
- **B7 — delete evicts** (unchanged): deleting a queued submission
  removes it from the queue first.

#### Submission payload

Captured at submit (Home click), stored in the queue entry: the
uploaded file reference + extracted prompt + recommended-settings flags
(platform=parallel, think-level/graph-viz from server settings,
graph_memory_update from server settings). Enough for the orchestrator
to run graph-build → create → prepare → run with zero further input.

#### Endpoints

- `POST /api/pipeline/submit` — accepts the file + prompt; decides
  start/queue/full; returns `{status: started|queued|full, ...}`.
- `/api/status` already exposes `running_simulations`, `queued_*`,
  `capacity_full` — extended so a pipeline in a pre-run step (graph
  build/prepare) still counts as occupying the slot (so a 2nd submit
  queues even before the run starts). This is the key correctness fix:
  the slot is occupied from graph-build, not from run.

#### Occupied-slot definition (the core correctness change)

A slot is occupied while a pipeline is in ANY step (graph build,
create, prepare, run) — not only when an OASIS subprocess is live.
The orchestrator marks its pipeline active on start and clears it on
terminal (report done / failed / cancelled). `submit`'s decision and
`capacity_full` read this active-pipeline count, not `list_running`.

## Backend design

- `PipelineOrchestrator`: runs one submission's steps in a daemon
  thread; marks active on entry, clears on exit; on exit calls
  `promote_next` to launch the oldest queued submission.
- Reuse `SimulationQueue` (slot=1, queue=2) but keyed on pipeline/submission.
- Thread-safe (submit from request threads, promote from orchestrator
  thread) via the existing lock.
- In-memory only (single process, ephemeral disk) — queued submissions
  lost on restart (accepted, matches prior stance). A pipeline mid-run
  is already killed by a restart today.

## Frontend design

- Both submit buttons (启动引擎 / 自动直达报告) → `POST /api/pipeline/submit`.
  **Stay on Home after submit** (do not auto-navigate) so the user can
  immediately queue the next project. The new card appears at once.
  - `started` → card shows 运行中; stay on Home.
  - `queued` → card shows 排队中; stay on Home.
  - `full` → start section already disabled; toast if raced.
- History card: **运行中** badge (Part 1) + existing 排队中 / 等待中 /
  取消排队. Both driven by `/api/status` (running + queued lists).
- Start section disabled on `capacity_full` (already built).
- Manual step-by-step flow kept for users who want to click through.
  Distinction: 自动直达报告 = server runs the whole chain unattended.
  启动引擎 (manual) = still creates the card instantly + occupies the
  slot, then the user drives the steps; but occupying the slot means a
  manual project also counts against concurrency (can't run 3 at once).
  If the slot is busy, a manual 启动引擎 also queues.

## Out of scope

- Reordering the queue (FIFO only).
- Per-UI configurable slot/queue (constants).
- Changing the manual step UI.

## Test matrix (TDD)

Backend: occupied-slot counts a pre-run pipeline (graph/prepare) so a
2nd submit queues; submit start/queue/full; promote-on-pipeline-done;
orchestrator marks/clears active; cancel drops queued payload; delete
evicts. Frontend: 运行中 badge from running list; 排队中 from queued
list; submit routes to pipeline endpoint; start disabled on capacity_full.
