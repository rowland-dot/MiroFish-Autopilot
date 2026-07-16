"""设置 API：思考深度（think level）等部署级运行时设置。

Spec: docs/specs/2026-07-16-think-level-toggle-spec.md
"""

from flask import Blueprint, jsonify, request

from ..utils.app_settings import THINK_LEVELS, get_think_level, set_setting

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('', methods=['GET'], strict_slashes=False)
def get_settings():
    """读取当前设置"""
    return jsonify({
        "success": True,
        "data": {"think_level": get_think_level()}
    })


@settings_bp.route('', methods=['POST'], strict_slashes=False)
def update_settings():
    """更新设置（仅允许已知取值）"""
    data = request.get_json(silent=True) or {}
    level = data.get('think_level')
    if level not in THINK_LEVELS:
        return jsonify({
            "success": False,
            "error": f"think_level must be one of {list(THINK_LEVELS)}"
        }), 400
    set_setting('think_level', level)
    return jsonify({"success": True, "data": {"think_level": level}})
