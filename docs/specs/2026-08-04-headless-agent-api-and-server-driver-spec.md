# Headless Agent API + Server-Side Pipeline Driver

**Status:** approved (2026-08-04)
**Slice:** v1 — submit / status / report

## Problem

Every MiroFish job today needs an open browser tab. The stage sequencing
(ontology → graph build → create → prepare → run → report) lives in
`frontend/src/services/pipelineDriver.js`; the server only exposes
individual stage endpoints and has no idea how to advance a job from one
to the next.

That blocks the whole class of headless use: an AI agent submitting a
document, a cron batch over a folder, a script in CI. It also means a
closed laptop stalls an in-flight job until a tab reopens.

## Goals

1. An AI agent can submit a simulation job, poll its state, and fetch the
   finished report — with no browser involved.
2. Headless jobs survive container restarts (Hugging Face restarts Spaces
   at will).
3. **Merge safety is a first-class requirement**: this fork rebases onto a
   busy upstream. The feature must add files, not edit upstream ones.

## Non-goals (v1)

- `cancel` / `list` CLI commands — the browser UI already does both, and
  agent jobs appear as ordinary cards.
- MCP server wrapper — trivial to add over this surface later; deliberately
  deferred so v1 ships.
- Settings (model / think level / caps) over the API — browser-only.

## Merge-safety contract

The fork's established pattern, used by 20+ shipped features with zero
merge conflicts: **new files under `backend/app/{api,services,utils}/`
plus a single registration line in `backend/app/__init__.py`** (a file the
fork already owns and reconciles by hand).

This feature adds three files and one registration line. It edits **no**
upstream file.

The server driver calls the **same HTTP endpoints the browser driver
calls**, over localhost, rather than importing upstream service classes.
Consequences:

- No duplicated orchestration logic to drift between the two drivers.
- Upstream refactors of service internals are absorbed automatically —
  the endpoint contract is the seam.
- Slight per-call overhead (localhost HTTP), irrelevant against stages
  measured in minutes.

## Architecture

| File | Ownership | Role |
|---|---|---|
| `backend/app/api/jobs.py` | new (fork) | REST surface: `POST /api/jobs`, `GET /api/jobs/<id>`, `GET /api/jobs/<id>/report` |
| `backend/app/services/job_driver.py` | new (fork) | Background thread; advances `mode: "agent"` pipeline entries |
| `cli/mirofish.py` | new (fork) | Standalone CLI, Python stdlib only (no install step) |
| `backend/app/__init__.py` | fork-owned edit | One blueprint registration + one driver start call |

### Queue integration

Agent jobs are ordinary pipeline entries (`backend/app/utils/pipeline_state.py`)
with `mode: "agent"`. Existing capacity rules apply unchanged: 1 running +
2 queued, shared across browser and agent submissions.

The browser driver only drives entries with `mode === 'auto'`
(`pipelineDriver.js`: `active.mode === 'auto'`, and `promoteHead` promotes
auto heads only), so it renders agent jobs as cards but never advances
them. No double-driving — the failure class that caused duplicate LLM
spend earlier in this project.

Cards, stage badges, cancel, and delete work on agent jobs with no
frontend change.

### Auth

The CLI authenticates with the existing access code (`MIROFISH_ACCESS_CODE`
env var), logging in and holding the session cookie itself — same gate the
browser uses. The server driver authenticates the same way for its
localhost calls, reading `ACCESS_CODE` from the Space environment.

Accepted trade-off: an agent config leak also exposes the human login. A
dedicated revocable API token is the cleaner long-term shape and can be
added later without changing the endpoint surface.

## Behavior contracts

Each contract is entry point → action → expected result, so tests can be
derived directly.

### B1 — Submit a job

- **Entry point:** agent with a document file and a prompt string.
- **Action:** `POST /api/jobs` (multipart: `file`, `prompt`).
- **Expected result:** HTTP 200 and
  `{"job_id": "tmp_<ts>_<n>", "status": "queued"}`. A pipeline entry
  exists with `mode: "agent"`, and a card appears in the browser history
  view within one poll cycle.
- **Capacity full:** HTTP 429 and
  `{"error": "queue full", "running": 1, "queued": 2}`. No entry created.
- **Missing file or prompt:** HTTP 400, no entry created.

### B2 — Poll job status

- **Entry point:** agent holding a `job_id`.
- **Action:** `GET /api/jobs/<job_id>`.
- **Expected result:** HTTP 200 with `{"job_id", "stage", "simulation_id",
  "report_id", "error"}` where `stage` is one of `queued | ontology |
  building | creating | preparing | running | reporting | done | failed`.
  When `stage == "running"`, the payload also carries `round` and
  `total_rounds`.
- **Unknown id:** HTTP 404.

### B3 — Fetch the report

- **Entry point:** agent whose job reached `done`.
- **Action:** `GET /api/jobs/<job_id>/report`.
- **Expected result:** HTTP 200, `text/markdown` body of the finished
  report.
- **Not finished yet:** HTTP 409 with `{"status": "<stage>"}` — never a
  partial report.
- **Job failed:** HTTP 409 with `{"status": "failed", "error": "<reason>"}`.

### B4 — Server driver advances an agent job unattended

- **Entry point:** an agent entry sitting at `queued` with no browser open.
- **Action:** none — the driver thread polls every 5 seconds.
- **Expected result:** the entry advances through ontology → build → create
  → prepare → run → report and finishes at `done`, with the report
  downloadable. Total wall time comparable to a browser-driven job.

### B5 — Restart resilience

- **Entry point:** an agent job mid-pipeline when the container restarts.
- **Action:** container boots.
- **Expected result:** the driver resumes that entry from its stored IDs
  (`projectId`, `graphId`, `simId`, `reportId`) without repeating a
  completed stage — no duplicate ontology, no restarted simulation, no
  regenerated report.

### B6 — Lifecycle semantics match the browser driver

The server driver reproduces the corrections already shipped for the
browser driver:

- Rounds-complete on a held-open process counts as run-finished (the OASIS
  subprocess intentionally stays alive awaiting interview commands).
- The report is generated **while the simulation process is alive**, so
  live agent interviews work, then the process is stopped.
- A job is `done` only when its report is **downloadable**, not when
  generation was merely kicked off.
- Transient 429/5xx are retried with backoff; plan-quota exhaustion fails
  fast with the provider's real message on the entry.

### B7 — Cancellation

- **Entry point:** user deletes an agent job's card in the browser (or the
  entry is removed via `DELETE /api/pipeline/<id>`).
- **Action:** existing delete path runs.
- **Expected result:** the driver abandons that entry at its next stage
  boundary; existing cancellation propagation stops its build/prepare/report
  tasks and simulation process. No orphaned work.

## Testing

Stage sequencing is extracted as dependency-injected pure functions,
mirroring the browser driver's `runOne` pattern, so the full pipeline is
exercised without network or LLM calls.

| Layer | Coverage |
|---|---|
| Unit | Stage advance logic per contract B4/B5/B6; capacity rejection (B1); status mapping (B2); report gating (B3) |
| API | Blueprint routes with a stubbed driver: 200/400/404/409/429 paths |
| Guard | The headless tests join `scripts/post-merge-check.sh`, so an upstream merge that breaks the headless path fails RED before deploy |

## Rollout

1. Land behind no flag — the surface is additive and inert until an agent
   posts a job.
2. Deploy during an idle window (deploy guard enforces this).
3. Validate live with one real end-to-end agent job before documenting the
   CLI in the fork README.

## Follow-ups (tracked, not in v1)

- MCP server wrapping the three commands as agent tools.
- Dedicated revocable API token (`MIROFISH_API_TOKEN`) alongside the access
  code.
- `cancel` and `list` CLI commands.
