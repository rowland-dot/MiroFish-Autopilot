"""备份 / 恢复 API：整份数据目录（uploads/）打包下载与还原。

两个接口都在 /api/ 下，AUTH_ENABLED 时自动受访问口令门保护。
Spec: docs/specs/2026-07-23-backup-restore-spec.md
"""

import io

from flask import Blueprint, current_app, jsonify, request, send_file

from ..config import Config
from ..utils.backup import make_backup_bytes, restore_from_bytes

backup_bp = Blueprint('backup', __name__)


def _data_dir() -> str:
    return current_app.config.get('UPLOAD_FOLDER') or Config.UPLOAD_FOLDER


@backup_bp.route('/backup', methods=['GET'])
def download_backup():
    """打包下载整个数据目录（.tar.gz）。"""
    data = make_backup_bytes(_data_dir())
    from datetime import datetime
    name = f"mirofish-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
    return send_file(
        io.BytesIO(data),
        as_attachment=True,
        download_name=name,
        mimetype='application/gzip',
    )


@backup_bp.route('/restore', methods=['POST'])
def upload_restore():
    """上传 .tar.gz 还原数据目录。"""
    file = request.files.get('archive')
    if file is None:
        return jsonify({"success": False, "error": "missing 'archive' file"}), 400
    try:
        count = restore_from_bytes(file.read(), _data_dir())
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    # 还原会把重启前的 run_state 一并带回来，其中可能有被重启杀掉、却仍写着
    # "running" 的僵尸记录（启动时的清理跑在还原之前，清不到它们）。
    import os
    from ..utils.run_state_reconcile import reconcile_on_start
    reconcile_on_start(os.path.join(_data_dir(), 'simulations'))

    return jsonify({"success": True, "restored_entries": count})
