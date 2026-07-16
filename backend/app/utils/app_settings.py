"""Server-persisted app settings (tiny JSON file store).

Holds deployment-wide runtime settings — currently the think level
(思考深度). One backend = one spend policy, so the setting is global.
Tolerant of a missing or corrupt file (falls back to defaults).

Spec: docs/specs/2026-07-16-think-level-toggle-spec.md
"""

import json
import os

from ..config import Config

# 思考深度: economy = 低思考量（省token，MiniMax已验证）; deep = 供应商原生行为
THINK_LEVELS = ("economy", "deep")
DEFAULT_THINK_LEVEL = "economy"

_DEFAULT_PATH = os.path.join(Config.UPLOAD_FOLDER, "app_settings.json")


def _load(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get_setting(key: str, default=None, path: str = None):
    """Read one setting; missing/corrupt file yields the default."""
    return _load(path or _DEFAULT_PATH).get(key, default)


def set_setting(key: str, value, path: str = None) -> None:
    """Persist one setting, preserving other keys; repairs a corrupt file."""
    target = path or _DEFAULT_PATH
    data = _load(target)
    data[key] = value
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_think_level(path: str = None) -> str:
    """Current think level; unknown/missing values sanitize to the default."""
    value = get_setting("think_level", DEFAULT_THINK_LEVEL, path=path)
    return value if value in THINK_LEVELS else DEFAULT_THINK_LEVEL
