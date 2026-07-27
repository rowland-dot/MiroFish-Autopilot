"""设置 API：思考深度（think level）等部署级运行时设置。

Spec: docs/specs/2026-07-16-think-level-toggle-spec.md
"""

import os

from flask import Blueprint, jsonify, request

from ..utils.app_settings import (
    ACTIVE_MODELS, BOOL_SETTINGS, THINK_LEVELS,
    get_active_model, get_bool, get_think_level, set_setting,
)

settings_bp = Blueprint('settings', __name__)


def _current():
    data = {"think_level": get_think_level(), "active_model": get_active_model()}
    data["deepseek_available"] = bool((os.environ.get("DEEPSEEK_API_KEY") or "").strip())
    for k in BOOL_SETTINGS:
        data[k] = get_bool(k)
    return data


@settings_bp.route('', methods=['GET'], strict_slashes=False)
def get_settings():
    """读取当前设置"""
    return jsonify({"success": True, "data": _current()})


@settings_bp.route('', methods=['POST'], strict_slashes=False)
def update_settings():
    """更新设置（仅允许已知键与取值）"""
    data = request.get_json(silent=True) or {}

    if 'think_level' in data:
        level = data.get('think_level')
        if level not in THINK_LEVELS:
            return jsonify({
                "success": False,
                "error": f"think_level must be one of {list(THINK_LEVELS)}"
            }), 400
        set_setting('think_level', level)

    if 'active_model' in data:
        m = data.get('active_model')
        if m not in ACTIVE_MODELS:
            return jsonify({
                "success": False,
                "error": f"active_model must be one of {list(ACTIVE_MODELS)}"
            }), 400
        set_setting('active_model', m)

    for key in BOOL_SETTINGS:
        if key in data:
            val = data.get(key)
            if not isinstance(val, bool):
                return jsonify({"success": False, "error": f"{key} must be a boolean"}), 400
            set_setting(key, val)

    return jsonify({"success": True, "data": _current()})
