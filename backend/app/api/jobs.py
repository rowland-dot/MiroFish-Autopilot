"""无头代理接口：提交 / 查询 / 取报告。

代理任务写入与浏览器任务同一份流水线状态（mode="agent"），因此历史卡片、
徽标、取消、删除全部自动生效；推进由 services/job_driver.py 的后台线程负责。
"""

import os
from datetime import datetime

from flask import Blueprint, jsonify, request

from ..config import Config
from ..services.job_store import (
    capacity_state, is_full, make_agent_entry, new_job_id,
)
from ..utils.pipeline_state import (
    default_path, load_entries, mutate_entries, upsert_entry,
)

jobs_bp = Blueprint('jobs', __name__)
_seq = {"n": 0}


def _ok(data, code=200):
    return jsonify({"success": True, "data": data}), code


def _err(data, code):
    return jsonify({"success": False, "data": data,
                    "error": data.get("error")}), code


@jobs_bp.route('', methods=['POST'], strict_slashes=False)
def submit_job():
    prompt = (request.form.get('prompt') or '').strip()
    upload = request.files.get('file')
    if not prompt or not upload or not upload.filename:
        return _err({"error": "file and prompt are required"}, 400)

    entries = load_entries(default_path())
    if is_full(entries):
        running, queued = capacity_state(entries)
        return _err({"error": "queue full", "running": running,
                     "queued": queued}, 429)

    now = datetime.now()
    _seq["n"] += 1
    job_id = new_job_id(now, _seq["n"])

    files_dir = os.path.join(Config.UPLOAD_FOLDER, "agent_uploads")
    os.makedirs(files_dir, exist_ok=True)
    upload.save(os.path.join(files_dir, f"{job_id}.bin"))

    entry = make_agent_entry(job_id, prompt, upload.filename, now)
    mutate_entries(default_path(), lambda es: upsert_entry(es, entry))
    return _ok({"job_id": job_id, "status": "queued"})


def _find(job_id):
    return next((e for e in load_entries(default_path())
                 if e.get("tmpId") == job_id), None)


@jobs_bp.route('/<job_id>', methods=['GET'])
def job_status(job_id):
    e = _find(job_id)
    if not e:
        return _err({"error": "unknown job"}, 404)
    data = {
        "job_id": job_id, "stage": e.get("status"),
        "simulation_id": e.get("simId"), "report_id": e.get("reportId"),
        "error": e.get("error"),
    }
    if e.get("status") == "running" and e.get("simId"):
        try:
            from ..services.simulation_runner import SimulationRunner
            rs = SimulationRunner.get_run_state(e["simId"])
            data["round"] = getattr(rs, "current_round", None)
            data["total_rounds"] = getattr(rs, "total_rounds", None)
        except Exception:
            pass
    return _ok(data)


@jobs_bp.route('/<job_id>/report', methods=['GET'])
def job_report(job_id):
    e = _find(job_id)
    if not e:
        return _err({"error": "unknown job"}, 404)
    if e.get("status") != "done" or not e.get("reportId"):
        return _err({"status": e.get("status"), "error": e.get("error")}, 409)

    from ..services.report_agent import ReportManager
    report = ReportManager.get_report(e["reportId"])
    if report is None:
        return _err({"error": "report record missing"}, 404)
    return (report.markdown_content or ""), 200, \
        {"Content-Type": "text/markdown; charset=utf-8"}
