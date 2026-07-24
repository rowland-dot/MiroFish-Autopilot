# Simulation Queue — Spec

**Date:** 2026-07-25
**Status:** Approved (mockup + decisions locked)
**Mockup:** queue-only, integrated into existing UX (no new page section)

## Problem

Free-tier HF Space (`cpu-basic`) has limited RAM. Two heavy OASIS
simulations running at once exceed it, and the Linux OOM-killer
SIGKILLs (`-9`) one subprocess — the run freezes silently mid-round,
no crash visible. Confirmed from Space logs 2026-07-24: `sim_47e174…`
killed `-9` at 10:34 and 12:03 while other runs were concurrent; the
container never restarted.

Root cause: nothing limits concurrent simulation starts.

## Solution

A queue with fixed capacity:

- **Slot** = concurrent RUNNING capacity. **1** (memory-safe hard limit).
- **Queue** = waiting line, not yet started, zero memory cost. **2**.
- **Total capacity** = 1 running + 2 queued = **3** jobs in the system.

Both values are single config constants, changeable later.

Integrated into existing UX only — **no new page section**:
1. History card gains a third status: **排队中** (queued), beside 运行中 / 完成.
2. Start section (both 启动引擎 and 自动直达报告 buttons) is **disabled**
   when the system is full (3 jobs). Otherwise untouched — its look and
   two-button behavior do NOT change.

## Behaviors (testable)

### B1 — idle start runs immediately
- **Entry:** home page, no simulation running or queued.
- **Action:** click 启动引擎 (or 自动直达报告).
- **Result:** simulation starts running immediately (current behavior,
  unchanged). Its card shows 运行中.

### B2 — start while running enqueues
- **Entry:** one simulation running (slot full), queue has < 2 entries.
- **Action:** click 启动引擎 (or 自动直达报告) for a new simulation.
- **Result:** the new simulation does NOT start. It enters the queue.
  Its history card shows the **排队中** badge + `等待中` in the round
  slot. No second subprocess spawns (memory safe). Start section stays
  enabled (a queue vacancy remains).

### B3 — full system disables start
- **Entry:** 1 running + 2 queued = 3 total.
- **Action:** (attempt to start a 4th).
- **Result:** the **start section is disabled** — both buttons greyed,
  not clickable. A short inline hint reads `队列已满 · 等空位` near the
  buttons. No new job can be created until a vacancy opens.

### B4 — auto-promote on completion
- **Entry:** 1 running + ≥1 queued.
- **Action:** the running simulation finishes (completed / failed /
  cancelled / env-closed).
- **Result:** the **oldest queued** simulation automatically starts
  running — no manual click. Its card flips 排队中 → 运行中. The freed
  queue slot re-enables the start section if it was disabled.

### B5 — cancel a queued job
- **Entry:** a simulation is 排队中.
- **Action:** click 取消排队 on its card.
- **Result:** the simulation is removed from the queue and reverts to
  **未开始** (ready, not started) — it stays in history as a normal
  card and can be started again later. Its project/config are NOT
  deleted (no data loss). The freed queue slot re-enables the start
  section if it was disabled. (Full permanent deletion remains the
  separate 🗑 delete-card action.)

### B7 — deleting a queued job evicts it from the queue
- **Entry:** a simulation is 排队中.
- **Action:** click 🗑 delete (the existing permanent-delete card action).
- **Result:** the id is removed from the queue **before** its folders
  are deleted, so auto-promote (B4) never tries to start a job whose
  config is gone. Then normal cascade delete runs. (Without this, a
  later promote would hit `模拟配置不存在` and crash — the queue must be
  evicted on delete of a queued id.)

### B6 — queued card appearance
- **Entry:** a simulation is 排队中.
- **Result:** history card shows: amber `排队中` corner badge; round
  slot reads `等待中` with an amber dot; a dashed `取消排队` button at
  the card bottom. Matches the approved mockup.

## Backend

Authoritative queue lives server-side (single source of truth; frontend
only reflects it).

- `SLOT_LIMIT = 1`, `QUEUE_LIMIT = 2` (config constants).
- **In-memory only**, no disk persistence. The app is a single Flask
  process (`app.run(threaded=True)`); the queue is a class-level FIFO
  structure alongside the existing `_run_states` / `_processes`. On a
  process restart the running subprocess is already dead and the disk
  may be wiped (HF ephemeral), so a persisted queue could never be
  safely promoted — persistence is dropped as YAGNI. Queued jobs are
  lost on restart/redeploy (accepted; consistent with the ephemeral
  stance). See `/api/status` note below.
- **Queue entry payload** = the start-request params needed to launch
  later, captured at enqueue time: `simulation_id`, `platform`,
  `max_rounds`, `enable_graph_memory_update` (+ resolved `graph_id`),
  `force`. Promotion re-invokes the existing start path with these.
  The queue holds the **request**, NOT a process — no subprocess spawns
  until promotion.
- A start request checks: running count < SLOT_LIMIT → start now; else
  queued count < QUEUE_LIMIT → enqueue; else reject with `queue_full`.
- **Promote trigger point:** the monitor loop's `finally` block
  (`simulation_runner.py` ~line 560) is the single chokepoint that runs
  whenever the running subprocess exits — covers completed / failed /
  stopped / env-closed. After it pops `_processes`, it dequeues the
  oldest queued entry (if any) and starts it. Because `SLOT_LIMIT = 1`
  there is only ever one running subprocess / monitor thread, so
  promotions cannot overlap. A lock guards the queue structure (mutated
  from the daemon monitor thread and from request threads).
- `/api/status` extends its existing shape (non-breaking) with: `queued`
  list (ordered ids) and `capacity_full` boolean — frontend disables the
  start section on `capacity_full`. **Deploy-gate note:** a queued-only
  system reports `busy: false` (no subprocess), so the deploy safety
  gate does not block on queued jobs — consistent with "queued jobs are
  ephemeral, lost on deploy."
- Cancel endpoint: remove a queued id, revert it to not-started
  (未开始). Distinct from delete (B7), which evicts from queue **and**
  removes the record.

## Frontend

- **排队中 is a new state, not a `RunnerStatus` enum value.** The card
  today derives its badge from round progress only (`getProgressClass`),
  where a queued sim (`current_round = 0`) would look identical to a
  never-started one. So the card must read the queued-id list from
  `/api/status` and mark any history card whose id is in `queued` as
  排队中 — the join is explicit (id ∈ queued), not inferred from rounds.
- History card: add 排队中 state (badge, 等待中 label, 取消排队 button).
- Start section: disable both buttons + show `队列已满 · 等空位` when
  `capacity_full`.
- Clicking start when slot busy shows a brief toast `已加入队列 ·
  当前推演结束后自动开始` (reuses existing toast pattern), then the new
  card appears 排队中.
- Poll queue state (reuse existing status polling) to flip cards and
  enable/disable the start section live.

## Out of scope

- Configurable slot/queue via UI (constants only, this pass).
- Priority / reordering the queue (FIFO only).
- MiniMax / Zep usage gauges (dropped).

## Test matrix (for TDD)

Backend unit: enqueue-when-busy, reject-when-full, FIFO promote-on-done,
cancel-reverts, delete-of-queued-evicts-queue (B7), capacity_full flag,
promote fires from monitor `finally`. Frontend: 排队中 card render driven
by id ∈ queued (not rounds), start section disabled on capacity_full,
cancel button calls endpoint + frees slot.
