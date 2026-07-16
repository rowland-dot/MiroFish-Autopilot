# Think-Level Toggle (思考深度) — lite spec

## Purpose
Make the reasoning-effort behavior a visible user choice instead of a
hardcoded value. Users switch between economical thinking (cheap, current
behavior) and the provider's stock full thinking, from the landing page.
Resolves the "silent hijack" problem: deep mode sends no thinking-control
parameter at all, restoring upstream/provider-default behavior.

## Modes
| Mode | Backend behavior | Notes |
|---|---|---|
| **经济 economy (default)** | `reasoning_effort="low"` on OASIS simulation agents and internal structured/JSON calls | ~50% completion-token savings; validated on MiniMax only |
| **🧠 深度 deep** | no thinking-control parameter sent anywhere | provider-stock behavior; compatible with any OpenAI-format API |

Invariant (both modes): the **report agent always runs full depth** — no
reasoning_effort is ever sent on report-writing calls. The chat_json
truncation safety net (16384 headroom + retry on parse failure) stays
unconditional; only the reasoning parameter becomes mode-dependent.

## Scope of the setting
Server-persisted, deployment-wide (one backend = one spend policy, shared by
the whole team). Applies to every run started after the switch (manual or
auto-pilot). Persists across backend restarts.

## Behaviors (entry → action → result)
1. **See current level.** Entry: landing page. Result: a "03 / 引擎设置" strip
   between the prompt box and the launch buttons shows a 思考深度 segmented
   control — **⚡ 经济 first, then 🧠 深度** (default leftmost) — with the
   active mode highlighted (loaded from `GET /api/settings`) and a one-line
   hint describing the active mode.
2. **Switch level.** Action: click the other segment. Result: `POST
   /api/settings` persists it; the control updates and shows ✓ 已保存 briefly.
   Applies to subsequent LLM calls (in-flight runs are not retro-changed).
3. **Backend read.** Every simulation-agent model build and every chat_json
   call reads the current mode at call time (including inside the simulation
   subprocess, which reads the same settings file).
4. **Missing/corrupt settings file.** Result: default `economy`; a POST
   recreates the file.

## Implementation shape
- `backend/app/utils/app_settings.py` — tiny JSON-file store
  (`uploads/app_settings.json`): `get_setting(key, default)`,
  `set_setting(key, value)`; tolerant of missing/corrupt file. Pure,
  pytest-covered.
- Key: `think_level` ∈ {`economy`, `deep`} (default `economy`; unknown values
  are treated as the default).
- `backend/app/api/settings.py` — blueprint: `GET /api/settings` returns
  `{think_level}`, `POST /api/settings` validates + persists. Registered in
  `create_app`; passcode gate applies automatically when enabled.
- `simulation_model.py` — `simulation_model_config()` returns
  `{"reasoning_effort": "low"}` in economy, `{}` in deep (read at call time).
- `llm_client.py` — `chat_json` sends `reasoning_effort="low"` only in
  economy; never in deep. Retry/headroom unchanged.
- Frontend: think-level strip in `Home.vue` per the approved mockup
  (segmented control + hint + ✓ 已保存), `getSettings`/`updateSettings` in a
  new `api/settings.js`. EN/ZH locale strings.

## Testing
- pytest: app_settings store (default on missing file, persist/reload,
  corrupt-file tolerance, unknown value → default); settings endpoint
  (GET default, POST persists, rejects invalid values);
  simulation_model_config per mode; chat_json param presence per mode.
- Browser-verify: toggle renders with current value, switch shows ✓ 已保存
  and survives reload.

## Out of scope
- Per-user think level (setting is deployment-wide by design).
- Provider capability detection beyond the two modes.
- Changing the report agent's depth (always full).
