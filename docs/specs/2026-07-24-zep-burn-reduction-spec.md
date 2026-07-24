# Zep Burn Reduction + Multi-Key Failover — lite spec

## Purpose
The free Zep plan's monthly credit (10,000 episodes) and per-window rate limit
(≈5 req/window) are being exhausted, failing jobs (429 "Rate limit exceeded for
FREE plan"). Cut Zep call volume WITHOUT hurting output quality, survive
transient limits, and fail over across multiple Zep accounts when one is spent.

## Zep's role (verified — do not break these)
- **Mandatory:** graph BUILD feeds agent-persona generation
  (`oasis_profile_generator` reads graph facts/summaries); the REPORT agent
  queries the graph (`zep_tools.insight_forge`, `panorama_search`). Keep both.
- **Cosmetic:** the graph VISUALIZATION (`getGraphData` polling) — display only.
- **Optional & the biggest burn:** the per-round simulation memory update
  (`enable_graph_memory_update`) floods episodes and produces the chatter graph.

## Components

### 1. Multi-Zep-key failover
- Config accepts multiple keys: `ZEP_API_KEY` (primary) + `ZEP_API_KEY_2`,
  `ZEP_API_KEY_3`… (or a comma-separated list).
- `zep_key_manager`: holds the ordered keys + the active index; `current()`
  returns the active key; `rotate()` advances to the next on an
  exhaustion/credit/429-after-retries error; raises when all are spent.
- Zep client construction (graph_builder, zep_tools) pulls the key from the
  manager and rotates on a hard failure. Registering a 2nd free account
  doubles monthly credit and unblocks immediately.

### 2. Per-round memory update → OFF by default (setting)
- New setting `graph_memory_update_enabled` (default **false**) in app_settings.
- Step 3's simulation start reads it (was hardcoded true). Default off stops the
  episode flood and the chatter graph. Report keeps built-graph GraphRAG + raw
  sim results, so quality is preserved. User can flip on per deployment.

### 3. Graph visualization → throttle + cache + optional toggle
- New setting `graph_viz_enabled` (default **true**). When false, the frontend
  does not poll `getGraphData` at all (zero viz reads).
- When true: frontend polling slowed (build 10s→30s, sim 30s→60s) and **stops
  once the graph task completes**; backend caches `/api/graph/data` per graph_id
  with a ~30s TTL so repeated polls/viewers cost one Zep read per window.

### 4. 429-aware retry/back-off on Zep calls
- Wrap Zep client calls so a `429`/rate error reads `retry-after`, waits, and
  retries (small bounded count) instead of failing the job; if still failing,
  trigger key rotation (#1) before giving up.

## Settings (server-persisted, deployment-wide, like think_level)
- `graph_memory_update_enabled`: bool, default false.
- `graph_viz_enabled`: bool, default true.
- Exposed via the existing `/api/settings` GET/POST (validated).

## Implementation shape
- `backend/app/utils/zep_key_manager.py` — ordered keys + rotate (pure, tested).
- `backend/app/utils/zep_retry.py` — `call_with_retry(fn, on_exhausted)` (tested with mocks).
- `backend/app/utils/graph_cache.py` — TTL cache (tested).
- `app_settings.py` + `/api/settings` — two new bool settings.
- `graph_builder.py` / `zep_tools.py` — construct Zep client via key manager;
  wrap calls with retry.
- `simulation_runner`/start path — read `graph_memory_update_enabled`.
- `api/graph.py get_graph_data` — serve via graph_cache.
- Frontend: poll intervals + stop-on-complete + honor `graph_viz_enabled`;
  memory-update flag from the setting. Settings UI toggles (later/minimal).

## Testing
- pytest: key-manager rotation (advance on failure, raise when exhausted);
  retry wrapper (429→retry→success; exhaust→rotate/raise); TTL cache (hit within
  TTL, miss after); settings default values + validation.
- Live (after Zep resets or 2nd key added): confirm poll rate dropped and a
  build succeeds on the fallback key.

## Out of scope
- Zep paid plan.
- Deeper graph-viz content redesign (ontology-core prioritization) — separate.
- Reducing graph BUILD episodes (kept; it's mandatory + modest).
