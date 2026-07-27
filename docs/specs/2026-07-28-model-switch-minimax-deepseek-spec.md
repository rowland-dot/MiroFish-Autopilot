# LLM Model Switch (MiniMax M3 ↔ DeepSeek V4 Pro) — Spec

**Date:** 2026-07-28
**Status:** Design approved (deployment-level). Awaiting spec sign-off.
**Scope:** A deployment-level toggle in section 03 to select which LLM
every simulation uses. No per-project selection (out of scope).

## Goal

Let the team switch the LLM the whole app uses between **MiniMax M3**
(current) and **DeepSeek V4 Pro** from a section-03 toggle, persisted
server-side like the existing 思考深度 / 实时图谱 settings, applying to
every LLM call.

## Verified facts (探测确认)

- DeepSeek endpoint `https://api.deepseek.com` (also `/v1`) responds;
  models are `deepseek-v4-flash` and **`deepseek-v4-pro`**. So the
  target model id is `deepseek-v4-pro`.
- LLM credentials are consumed via **two distinct paths**:
  1. **In-process constructors** reading `Config.LLM_*` and building an
     `OpenAI(...)` client — **3 sites**: `utils/llm_client.py:100`
     (`LLMClient`, the core client), `oasis_profile_generator.py:251`,
     `simulation_config_generator.py:232`. Consumers that build
     `LLMClient()` (ontology_generator, report_agent, zep_tools) ride
     along transitively once `LLMClient` reroutes — no separate work.
  2. **The OASIS simulation subprocess** (the highest-volume consumer —
     every agent, every round). `simulation_runner.py:679` spawns
     `run_{twitter,reddit,parallel}_simulation.py` via `Popen` with
     `env = os.environ.copy()` and **no LLM override**. Those scripts
     build the agent model via `ModelFactory.create(...)` reading **raw
     `os.environ` `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME`**
     (`run_*_simulation.py`). They never touch `resolve_llm` or
     `app_settings`.
- Therefore the switch MUST reach BOTH paths, or it silently only
  affects pre/post generators while the actual simulation keeps running
  on the env-configured provider.

## Design

### Setting
`active_model` ∈ {`minimax-m3`, `deepseek-v4-pro`}, stored in
`app_settings.json` (server-persisted, whole-team), default
`minimax-m3`. Mirrors the existing `think_level` string setting.

### Provider config (a resolver, single routing point)
A pure `resolve_llm(active_model, env)` returns
`{api_key, base_url, model}`:

- `minimax-m3` → `env.LLM_API_KEY`, `env.LLM_BASE_URL`
  (default `https://api.minimaxi.com/v1`), model `MiniMax-M3`.
- `deepseek-v4-pro` → `env.DEEPSEEK_API_KEY`,
  base `https://api.deepseek.com`, model `deepseek-v4-pro` (constants).

**Path 1 — in-process (3 constructor sites).** `LLMClient`,
`oasis_profile_generator`, `simulation_config_generator` default their
`api_key/base_url/model` to `resolve_llm(get_active_model(), os.environ)`
instead of `Config.LLM_*`. Explicit constructor args still win.
ontology_generator / report_agent / zep_tools inherit via `LLMClient`.

**IMPLEMENTATION NOTE (avoid the import-time trap):** resolve in the
constructor **body**, mirroring the existing `self.x = arg or
Config.LLM_*` line — e.g. `self.api_key = api_key or _r['api_key']`
where `_r = resolve_llm(get_active_model(), os.environ)` is computed
inside `__init__`. NEVER as a signature default
(`def __init__(self, api_key=resolve_llm(...))`) — Python evaluates
signature defaults once at import, which would freeze the model at boot
and defeat mid-session switching. `app_settings._load()` reads the file
fresh per call, so a body-resolve reflects the current toggle on each
construction.

**Path 2 — the OASIS simulation subprocess (the critical reroute).**
In `simulation_runner.py`, BEFORE `Popen`, compute
`resolve_llm(get_active_model(), os.environ)` and set the resolved
`api_key / base_url / model` onto the **copied env** the subprocess
inherits (`env['LLM_API_KEY'] = ...`, `env['LLM_BASE_URL'] = ...`,
`env['LLM_MODEL_NAME'] = ...`). The `run_*_simulation.py` scripts stay
unchanged — they keep reading those env vars via `ModelFactory`, now
carrying the selected provider's creds. This is the smallest change
that makes the switch actually reach the agents.

### API
`/api/settings` GET returns `active_model` alongside the existing keys,
plus `deepseek_available` (bool = `DEEPSEEK_API_KEY` is set & non-blank)
so the UI can warn when DeepSeek is selected but unconfigured. POST
validates `active_model` ∈ the 2 values (400 otherwise) and persists it.

### UI
A new toggle row in section 03 (mirrors 思考深度): `MiniMax M3` /
`DeepSeek V4 Pro`. POSTs `active_model`, persisted, loaded on mount.

### Error handling / fallback
If `active_model=deepseek-v4-pro` but `DEEPSEEK_API_KEY` is unset/blank,
`resolve_llm` falls back to the MiniMax config and logs a warning —
never hard-fails a run over a missing key.

### Secret
`DEEPSEEK_API_KEY` is added as a Space secret at deploy time (never in
the repo). Exact console steps provided at deploy.

## Behaviors (testable)

- **B1 — persist.** POST `/api/settings {active_model:'deepseek-v4-pro'}`
  → GET `/api/settings` returns `active_model:'deepseek-v4-pro'`.
- **B2 — resolve MiniMax.** `resolve_llm('minimax-m3', env)` →
  `{api_key: env.LLM_API_KEY, base_url: env.LLM_BASE_URL||default,
  model: 'MiniMax-M3'}`.
- **B3 — resolve DeepSeek.** `resolve_llm('deepseek-v4-pro', env)` →
  `{api_key: env.DEEPSEEK_API_KEY, base_url: 'https://api.deepseek.com',
  model: 'deepseek-v4-pro'}`.
- **B4 — missing-key fallback.** `resolve_llm('deepseek-v4-pro', env)`
  with no `DEEPSEEK_API_KEY` → returns the MiniMax config (not a crash).
- **B5 — invalid rejected.** POST `active_model:'gpt-9'` → 400, setting
  unchanged.
- **B6 — UI toggle.** Section 03 shows a MiniMax M3 / DeepSeek V4 Pro
  toggle reflecting the saved value; clicking DeepSeek POSTs and shows
  saved; reload keeps it.
- **B7 — pre/post generators use the active model.** With
  `active_model=deepseek-v4-pro`, `LLMClient` /
  `oasis_profile_generator` / `simulation_config_generator` (and the
  LLMClient-based ontology/report/zep consumers) build with the DeepSeek
  config (constructor body defaults to `resolve_llm`).
- **B8 — simulation subprocess uses the active model (the critical
  one).** With `active_model=deepseek-v4-pro`, the env passed to the
  OASIS `Popen` carries `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL_NAME`
  = the DeepSeek resolved values, so the agents run on DeepSeek. Testable
  by asserting the env dict built for the subprocess (extract that
  env-building into a pure helper `build_sim_env(base_env, active_model)`
  and unit-test it) rather than launching a real subprocess.
- **B9 — deepseek_available surfaced.** GET `/api/settings` includes
  `deepseek_available`; false when `DEEPSEEK_API_KEY` is unset.

## Backend

- `app_settings.py`: add `active_model` to the string settings with
  `ACTIVE_MODELS = ("minimax-m3","deepseek-v4-pro")`, `DEFAULT_ACTIVE_MODEL
  = "minimax-m3"`, `get_active_model()` (copy the `think_level` pattern).
- `resolve_llm.py` (new util): pure `resolve_llm(active_model, env)` →
  `{api_key, base_url, model}`, with the missing-DeepSeek-key → MiniMax
  fallback. Also `build_sim_env(base_env, active_model)` → a copy of
  `base_env` with `LLM_API_KEY/LLM_BASE_URL/LLM_MODEL_NAME` set to the
  resolved values (for the subprocess). When active=DeepSeek it ALSO
  overrides the optional boost vars `LLM_BOOST_API_KEY/LLM_BOOST_BASE_URL/
  LLM_BOOST_MODEL_NAME` to the same DeepSeek values (else a boost-
  configured deployment would leave parallel-sim Reddit agents on the
  boost provider after the toggle — dormant by default, but closed here).
  For MiniMax, boost vars are left untouched.
- `settings.py` API: include `active_model` + `deepseek_available` in GET;
  validate `active_model` in POST.
- **Path-1 constructors** (`LLMClient`, `oasis_profile_generator`,
  `simulation_config_generator`): default in the body to
  `resolve_llm(get_active_model(), os.environ)` (keep explicit-arg override).
- **Path-2 subprocess** (`simulation_runner.py`): before `Popen`, replace
  the plain `env = os.environ.copy()` with
  `env = build_sim_env(os.environ, get_active_model())`.
- `config.py`: add `DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')`.

## Frontend

- `Home.vue` section 03: add a model toggle row (like the think-level
  seg), bound to `active_model`; `setModel()` POSTs; onMounted loads.
- `api/settings.js` already covers GET/POST settings; extend payload.
- Locale strings: `modelLabel`, `modelMinimax`, `modelDeepseek`, hint.

## Out of scope

- Per-project model selection (moves to per-run submission; not now).
- Adding more than these two models (the resolver is extensible, but
  the UI ships exactly two).
- deepseek-v4-flash (only `-pro` per the request).

## Test matrix (TDD)

Backend unit: `resolve_llm` for each active value + missing-key
fallback (B2–B4); `build_sim_env` sets the DeepSeek creds on the copied
env when active=deepseek (B8 — the critical one); settings persistence +
invalid rejection + `deepseek_available` (B1, B5, B9); a Path-1
constructor defaults to the DeepSeek config when active=deepseek (B7).
Frontend: section-03 model toggle renders from saved value + POSTs on
change (B6).
