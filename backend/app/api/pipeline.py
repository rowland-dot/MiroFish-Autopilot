"""流水线状态 API：队列与卡片状态的服务器端存储。

独立蓝图，不改动上游文件（fork 需频繁与 upstream 同步）。
位于 /api/ 下，自动继承访问口令门（app 级 before_request，见 auth.py）。

Spec: docs/specs/2026-07-28-server-persisted-pipeline-state-spec.md
"""

from flask import Blueprint, jsonify, request

from ..utils.pipeline_state import (
    default_path, mutate_entries, prune_entries, remove_entry, upsert_entry,
)

pipeline_bp = Blueprint('pipeline', __name__)


def _ok(entries):
    return jsonify({"success": True, "data": {"entries": entries}})


@pipeline_bp.route('', methods=['GET'], strict_slashes=False)
def get_pipeline():
    """读取条目（顺带清理并落盘，避免只读时文件无限增长）。"""
    return _ok(mutate_entries(default_path(), lambda es: prune_entries(es)))


@pipeline_bp.route('', methods=['POST'], strict_slashes=False)
def upsert_pipeline():
    """新增/更新一条（按 tmpId）。"""
    entry = request.get_json(silent=True) or {}
    if not entry.get('tmpId'):
        return jsonify({"success": False, "error": "tmpId is required"}), 400
    return _ok(mutate_entries(
        default_path(), lambda es: prune_entries(upsert_entry(es, entry))))


@pipeline_bp.route('/<tmp_id>', methods=['DELETE'])
def delete_pipeline(tmp_id):
    """删除一条（取消排队 / 清理）。未知 id 也返回 200，便于幂等重试。"""
    return _ok(mutate_entries(
        default_path(), lambda es: prune_entries(remove_entry(es, tmp_id))))
