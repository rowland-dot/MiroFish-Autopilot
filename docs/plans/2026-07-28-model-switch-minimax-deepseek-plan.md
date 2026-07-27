# LLM Model Switch (MiniMax M3 ↔ DeepSeek V4 Pro) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A deployment-level section-03 toggle that switches every LLM call (in-process generators AND the OASIS simulation subprocess) between MiniMax M3 and DeepSeek V4 Pro.

**Architecture:** A pure `resolve_llm(active_model, env)` returns `{api_key, base_url, model}` for the selected provider (MiniMax from `LLM_*`, DeepSeek from `DEEPSEEK_API_KEY` + constants, missing-key→MiniMax fallback). `active_model` persists in `app_settings.json` like `think_level`. Three in-process constructors default to `resolve_llm` in their `__init__` body; the simulation subprocess gets `build_sim_env(os.environ, active_model)` before `Popen`. UI adds a section-03 seg toggle.

**Tech Stack:** Python/Flask + pytest (backend), Vue 3 `<script setup>` (frontend). Spec: `docs/specs/2026-07-28-model-switch-minimax-deepseek-spec.md`. venv python: `backend/.venv/Scripts/python.exe`.

---

## File structure

**Create:** `backend/app/utils/resolve_llm.py` (resolve_llm + build_sim_env), `backend/tests/test_resolve_llm.py`.
**Modify:** `backend/app/utils/app_settings.py` (ACTIVE_MODELS + get_active_model), `backend/app/api/settings.py` (active_model + deepseek_available), `backend/app/config.py` (DEEPSEEK_API_KEY), `backend/app/utils/llm_client.py` + `backend/app/services/oasis_profile_generator.py` + `backend/app/services/simulation_config_generator.py` (constructor bodies), `backend/app/services/simulation_runner.py` (subprocess env), `backend/tests/test_app_settings.py` + `backend/tests/test_settings_api.py` (or existing), `frontend/src/views/Home.vue`, `locales/en.json` + `locales/zh.json`.

---

## Task 1: resolve_llm + build_sim_env (pure, TDD)

**Files:** Create `backend/app/utils/resolve_llm.py`, `backend/tests/test_resolve_llm.py`

- [ ] **Step 1: Write failing tests**

```python
from app.utils.resolve_llm import resolve_llm, build_sim_env

MINIMAX_ENV = {"LLM_API_KEY": "mm_key", "LLM_BASE_URL": "https://api.minimaxi.com/v1"}
DS_ENV = {**MINIMAX_ENV, "DEEPSEEK_API_KEY": "ds_key"}

def test_resolve_minimax():
    r = resolve_llm("minimax-m3", MINIMAX_ENV)
    assert r == {"api_key": "mm_key", "base_url": "https://api.minimaxi.com/v1", "model": "MiniMax-M3"}

def test_resolve_minimax_base_default():
    r = resolve_llm("minimax-m3", {"LLM_API_KEY": "mm_key"})
    assert r["base_url"] == "https://api.minimaxi.com/v1"   # default when unset

def test_resolve_deepseek():
    r = resolve_llm("deepseek-v4-pro", DS_ENV)
    assert r == {"api_key": "ds_key", "base_url": "https://api.deepseek.com", "model": "deepseek-v4-pro"}

def test_resolve_deepseek_missing_key_falls_back_to_minimax():
    r = resolve_llm("deepseek-v4-pro", MINIMAX_ENV)   # no DEEPSEEK_API_KEY
    assert r["model"] == "MiniMax-M3" and r["api_key"] == "mm_key"

def test_resolve_unknown_falls_back_to_minimax():
    assert resolve_llm("gpt-9", MINIMAX_ENV)["model"] == "MiniMax-M3"

def test_build_sim_env_minimax_untouched():
    env = build_sim_env({"LLM_API_KEY": "mm_key", "X": "1"}, "minimax-m3")
    assert env["LLM_API_KEY"] == "mm_key" and env["LLM_MODEL_NAME"] == "MiniMax-M3" and env["X"] == "1"

def test_build_sim_env_deepseek_overrides_general_and_boost():
    env = build_sim_env(DS_ENV, "deepseek-v4-pro")
    assert env["LLM_API_KEY"] == "ds_key"
    assert env["LLM_BASE_URL"] == "https://api.deepseek.com"
    assert env["LLM_MODEL_NAME"] == "deepseek-v4-pro"
    assert env["LLM_BOOST_API_KEY"] == "ds_key"          # boost also switched
    assert env["LLM_BOOST_MODEL_NAME"] == "deepseek-v4-pro"

def test_build_sim_env_returns_copy():
    base = {"LLM_API_KEY": "mm_key"}
    build_sim_env(base, "deepseek-v4-pro")
    assert base == {"LLM_API_KEY": "mm_key"}              # original not mutated
```

- [ ] **Step 2: Run → FAIL** — `./.venv/Scripts/python.exe -m pytest tests/test_resolve_llm.py -q`

- [ ] **Step 3: Implement**

```python
# backend/app/utils/resolve_llm.py
"""Resolve LLM credentials for the active model (deployment-level switch).

Two providers: MiniMax M3 (env LLM_*) and DeepSeek V4 Pro (env
DEEPSEEK_API_KEY + fixed base/model). If DeepSeek is selected but its key
is missing/blank, fall back to MiniMax (never hard-fail a run).
"""

MINIMAX_MODEL = "MiniMax-M3"
MINIMAX_BASE_DEFAULT = "https://api.minimaxi.com/v1"
DEEPSEEK_MODEL = "deepseek-v4-pro"
DEEPSEEK_BASE = "https://api.deepseek.com"


def _minimax(env):
    return {
        "api_key": env.get("LLM_API_KEY"),
        "base_url": env.get("LLM_BASE_URL") or MINIMAX_BASE_DEFAULT,
        "model": MINIMAX_MODEL,
    }


def resolve_llm(active_model, env):
    if active_model == "deepseek-v4-pro":
        key = (env.get("DEEPSEEK_API_KEY") or "").strip()
        if key:
            return {"api_key": key, "base_url": DEEPSEEK_BASE, "model": DEEPSEEK_MODEL}
        return _minimax(env)          # missing key -> fallback
    return _minimax(env)              # minimax-m3 + any unknown


def build_sim_env(base_env, active_model):
    """Copy base_env with LLM_* (and, for DeepSeek, LLM_BOOST_*) set to the
    resolved provider so the OASIS subprocess agents use the active model."""
    env = dict(base_env)
    r = resolve_llm(active_model, base_env)
    env["LLM_API_KEY"] = r["api_key"] or ""
    env["LLM_BASE_URL"] = r["base_url"]
    env["LLM_MODEL_NAME"] = r["model"]
    if active_model == "deepseek-v4-pro" and (base_env.get("DEEPSEEK_API_KEY") or "").strip():
        env["LLM_BOOST_API_KEY"] = r["api_key"]
        env["LLM_BOOST_BASE_URL"] = r["base_url"]
        env["LLM_BOOST_MODEL_NAME"] = r["model"]
    return env
```

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** — `git add backend/app/utils/resolve_llm.py backend/tests/test_resolve_llm.py && git commit -m "feat: resolve_llm + build_sim_env (model provider routing)"`

---

## Task 2: app_settings active_model (TDD)

**Files:** Modify `backend/app/utils/app_settings.py`, extend `backend/tests/test_app_settings.py`

- [ ] **Step 1: Failing test**

```python
from app.utils.app_settings import get_active_model, set_setting, ACTIVE_MODELS

def test_active_model_default_and_persist(tmp_path):
    p = str(tmp_path / "s.json")
    assert get_active_model(path=p) == "minimax-m3"          # default
    set_setting("active_model", "deepseek-v4-pro", path=p)
    assert get_active_model(path=p) == "deepseek-v4-pro"

def test_active_model_unknown_sanitizes_to_default(tmp_path):
    p = str(tmp_path / "s.json")
    set_setting("active_model", "gpt-9", path=p)
    assert get_active_model(path=p) == "minimax-m3"
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implement** — after the THINK_LEVELS block in `app_settings.py`:

```python
ACTIVE_MODELS = ("minimax-m3", "deepseek-v4-pro")
DEFAULT_ACTIVE_MODEL = "minimax-m3"


def get_active_model(path: str = None) -> str:
    value = get_setting("active_model", DEFAULT_ACTIVE_MODEL, path=path)
    return value if value in ACTIVE_MODELS else DEFAULT_ACTIVE_MODEL
```

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** — `git commit -am "feat: active_model app setting (allowlist + default)"`

---

## Task 3: config DEEPSEEK_API_KEY

**Files:** Modify `backend/app/config.py`

- [ ] **Step 1:** Add near `LLM_MODEL_NAME`: `DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')`
- [ ] **Step 2:** `./.venv/Scripts/python.exe -c "from app import create_app; create_app(); print('OK')"`
- [ ] **Step 3: Commit** — `git commit -am "chore: DEEPSEEK_API_KEY config"`

---

## Task 4: settings API — active_model + deepseek_available (TDD)

**Files:** Modify `backend/app/api/settings.py`, extend `backend/tests/test_settings_api.py`

- [ ] **Step 1: Failing tests** (use the app test client; mirror existing think_level tests)

```python
def test_get_settings_includes_active_model_and_deepseek_available(client):
    r = client.get('/api/settings').get_json()['data']
    assert r['active_model'] in ('minimax-m3', 'deepseek-v4-pro')
    assert isinstance(r['deepseek_available'], bool)

def test_deepseek_available_false_when_key_unset(client, monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    assert client.get('/api/settings').get_json()['data']['deepseek_available'] is False

def test_deepseek_available_true_when_key_set(client, monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'ds_key')
    assert client.get('/api/settings').get_json()['data']['deepseek_available'] is True

def test_post_active_model_valid(client):
    r = client.post('/api/settings', json={'active_model': 'deepseek-v4-pro'})
    assert r.get_json()['data']['active_model'] == 'deepseek-v4-pro'

def test_post_active_model_invalid_400(client):
    r = client.post('/api/settings', json={'active_model': 'gpt-9'})
    assert r.status_code == 400
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implement** — in `settings.py`:
  - Add `import os` at the top (the file currently imports only from `app_settings`).
  - import `ACTIVE_MODELS, get_active_model` from `..utils.app_settings`.
  - `_current()` add: `data["active_model"] = get_active_model()` and
    `data["deepseek_available"] = bool((os.environ.get("DEEPSEEK_API_KEY") or "").strip())`.
  - In `update_settings`, add a block mirroring think_level:

```python
    if 'active_model' in data:
        m = data.get('active_model')
        if m not in ACTIVE_MODELS:
            return jsonify({"success": False, "error": f"active_model must be one of {list(ACTIVE_MODELS)}"}), 400
        set_setting('active_model', m)
```

- [ ] **Step 4: Run → PASS**
- [ ] **Step 5: Commit** — `git commit -am "feat: /api/settings active_model + deepseek_available"`

---

## Task 5: Path-1 constructors default to resolve_llm (TDD)

**Files:** Modify `llm_client.py`, `oasis_profile_generator.py`, `simulation_config_generator.py`; test in `backend/tests/test_resolve_llm.py` (constructor wiring)

Pattern for EACH of the three `__init__` bodies — replace the three
`Config.LLM_*` fallbacks with a resolved dict (body-resolve, NOT a
signature default):

```python
        from ..utils.resolve_llm import resolve_llm
        from ..utils.app_settings import get_active_model
        import os
        _r = resolve_llm(get_active_model(), os.environ)
        self.api_key = api_key or _r["api_key"]
        self.base_url = base_url or _r["base_url"]
        self.model = model or _r["model"]        # llm_client ONLY
```
**Per-file exact lines (param AND attr names differ — do NOT copy the
snippet verbatim into the generators):**
- `llm_client.py`: param `model`, attr `self.model` →
  `self.model = model or _r["model"]`
- `oasis_profile_generator.py`: param `model_name`, attr `self.model_name` →
  `self.model_name = model_name or _r["model"]`
- `simulation_config_generator.py`: param `model_name`, attr `self.model_name` →
  `self.model_name = model_name or _r["model"]`

The `api_key`/`base_url` lines are identical in all three:
`self.api_key = api_key or _r["api_key"]`, `self.base_url = base_url or _r["base_url"]`.

- [ ] **Step 1: Failing test** (LLMClient picks up DeepSeek when active + env set)

```python
def test_llmclient_uses_active_model(monkeypatch, tmp_path):
    import os
    from app.utils import app_settings
    monkeypatch.setenv("LLM_API_KEY", "mm_key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds_key")
    p = str(tmp_path / "s.json")
    monkeypatch.setattr(app_settings, "_DEFAULT_PATH", p)
    app_settings.set_setting("active_model", "deepseek-v4-pro", path=p)
    from app.utils.llm_client import LLMClient
    c = LLMClient()
    assert c.model == "deepseek-v4-pro" and c.base_url == "https://api.deepseek.com"
```

- [ ] **Step 2: Run → FAIL**
- [ ] **Step 3: Implement** the body-resolve in all three constructors.
- [ ] **Step 4: Run → PASS**; also run full suite `pytest -q` (no regressions).
- [ ] **Step 5: Commit** — `git commit -am "feat: LLM constructors default to active-model provider"`

---

## Task 6: Path-2 subprocess env (the critical reroute)

**Files:** Modify `backend/app/services/simulation_runner.py` (~line 673)

- [ ] **Step 1:** Replace `env = os.environ.copy()` (line 673) with:

```python
            from ..utils.resolve_llm import build_sim_env
            from ..utils.app_settings import get_active_model
            env = build_sim_env(os.environ, get_active_model())
```
(Keep the following `env['PYTHONUTF8']` / `env['PYTHONIOENCODING']` lines — they layer on top.)

- [ ] **Step 2:** App boots: `./.venv/Scripts/python.exe -c "from app import create_app; create_app(); print('OK')"`. (B8 behavior is already unit-tested via `build_sim_env` in Task 1 — no real subprocess needed.)
- [ ] **Step 3: Commit** — `git commit -am "feat: OASIS subprocess inherits the active model's LLM creds"`

---

## Task 7: Frontend section-03 model toggle

**Files:** Modify `frontend/src/views/Home.vue`, `locales/en.json`, `locales/zh.json`

- [ ] **Step 1:** In `Home.vue` section 03 (after the 实时图谱 `tl-row`), add a model row mirroring the think-level seg:

```html
<div class="think-level" style="margin-top:8px;">
  <span class="tl-label">{{ $t('home.modelLabel') }}</span>
  <div class="tl-seg">
    <button class="tl-opt" :class="{ active: activeModel === 'minimax-m3' }" @click="setModel('minimax-m3')">MiniMax M3</button>
    <button class="tl-opt" :class="{ active: activeModel === 'deepseek-v4-pro' }" :disabled="!deepseekAvailable" @click="setModel('deepseek-v4-pro')">DeepSeek V4 Pro</button>
  </div>
  <span v-if="!deepseekAvailable" class="tl-hint">{{ $t('home.modelDeepseekUnavailable') }}</span>
  <span v-if="modelSaved" class="tl-saved">✓ {{ $t('home.thinkLevelSaved') }}</span>
</div>
```
(Outer wrapper is `class="think-level"` to match the existing 思考深度 /
实时图谱 rows — NOT `tl-row`, which doesn't exist. Product names
"MiniMax M3" / "DeepSeek V4 Pro" are intentionally not translated.)

- [ ] **Step 2:** Script (mirror `graphVizEnabled`/`setGraphViz`): add `activeModel = ref('minimax-m3')`, `deepseekAvailable = ref(false)`, `modelSaved = ref(false)`. In the existing `onMounted` settings load, set `activeModel.value = res.data.active_model || 'minimax-m3'` and `deepseekAvailable.value = !!res.data.deepseek_available`. Add:

```js
const setModel = async (m) => {
  if (m === activeModel.value) return
  if (m === 'deepseek-v4-pro' && !deepseekAvailable.value) return
  const prev = activeModel.value
  activeModel.value = m
  try { await updateSettings({ active_model: m }); modelSaved.value = true; setTimeout(() => modelSaved.value = false, 2000) }
  catch { activeModel.value = prev }
}
```

- [ ] **Step 3:** Locale keys (en + zh): `modelLabel` (模型 / Model), `modelDeepseekUnavailable` ("DeepSeek 密钥未配置——当前使用 MiniMax" / "DeepSeek key not set — using MiniMax").
- [ ] **Step 4:** `cd frontend && npm run build` — clean. (B6 is verified
  manually on the Space in Task 8 — the repo has no frontend test infra,
  all automated tests are backend pytest.)
- [ ] **Step 5: Commit** — `git commit -am "feat: section-03 MiniMax/DeepSeek model toggle"`

---

## Task 8: verify + deploy (one deploy)

- [ ] **Step 1:** `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q` — all pass. `cd frontend && npm run build` — clean.
- [ ] **Step 2:** Merge branch → main.
- [ ] **Step 3:** Add Space secret `DEEPSEEK_API_KEY` (value provided by user) BEFORE deploy — walk the user through the settings page (secrets-first, so the rebuild picks it up). Then **one** safe deploy `bash scripts/deploy_hf.sh` (backs up first; aborts if it can't).
- [ ] **Step 4:** Verify live: GET `/api/settings` shows `active_model` + `deepseek_available:true`; toggle to DeepSeek, start a small run, confirm it uses DeepSeek.
- [ ] **Step 5:** Delete branch.

---

## Notes
- **Never** put `DEEPSEEK_API_KEY` in the repo — Space secret only.
- Body-resolve in constructors, never a signature default (import-time freeze).
- `build_sim_env` is the ONLY thing that makes the switch reach the actual simulation agents — do not skip Task 6.
