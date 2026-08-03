"""服务端任务驱动器：无需浏览器即可推进代理任务。

只驱动 mode == "agent" 的条目；浏览器条目（auto/manual）由浏览器驱动器
负责，双方共用同一份容量（1 运行 + 2 排队），因此绝不会双驱动。
通过 localhost 调用与浏览器完全相同的 HTTP 端点——上游重构服务内部实现
时自动跟随，不改动任何上游文件。
"""

import os
import threading
import time

import requests

from ..utils.logger import logger
from ..utils.pipeline_state import (
    default_path, load_entries, mutate_entries, upsert_entry,
)
from .job_stages import advance
from .job_store import ACTIVE_STATUSES

POLL_SECONDS = 5


def pick_next(entries: list):
    """要推进的代理条目：优先已活跃的；无任何活跃条目时才提升排队队首。"""
    active = [e for e in entries if e.get("status") in ACTIVE_STATUSES]
    for e in active:
        if e.get("mode") == "agent":
            return e
    if active:
        return None          # 浏览器任务占着槽位——代理任务等待
    return next((e for e in entries
                 if e.get("mode") == "agent" and e.get("status") == "queued"), None)


class LocalHttp:
    """本机 HTTP 客户端，携带访问口令会话（与浏览器同一道门）。"""

    def __init__(self, base_url: str, access_code: str):
        self.base = base_url.rstrip("/")
        self.code = access_code
        self.session = requests.Session()
        self._logged_in = False

    def _login(self):
        if self._logged_in or not self.code:
            return
        self.session.post(f"{self.base}/api/auth/login",
                          json={"code": self.code}, timeout=30)
        self._logged_in = True

    def _unwrap(self, resp):
        resp.raise_for_status()
        body = resp.json()
        return body.get("data", body) if isinstance(body, dict) else body

    def get(self, path):
        self._login()
        return self._unwrap(self.session.get(f"{self.base}{path}", timeout=60))

    def post(self, path, json=None):
        self._login()
        return self._unwrap(self.session.post(f"{self.base}{path}", json=json,
                                              timeout=300))

    def post_file(self, path, file_bytes, file_name, fields):
        self._login()
        files = {"files": (file_name, file_bytes)}
        return self._unwrap(self.session.post(f"{self.base}{path}", files=files,
                                              data=fields, timeout=600))


def _persist(entry: dict):
    mutate_entries(default_path(), lambda es: upsert_entry(es, entry))


def _loop(base_url: str, access_code: str, files_dir: str):
    http = LocalHttp(base_url, access_code)
    while True:
        try:
            entry = pick_next(load_entries(default_path()))
            if entry:
                path = os.path.join(files_dir, f"{entry['tmpId']}.bin")
                with open(path, "rb") as f:
                    file_bytes = f.read()
                if entry["status"] == "queued":
                    entry = {**entry, "status": "ontology"}
                    _persist(entry)

                def _still_there(job_id=entry["tmpId"]):
                    return not any(x.get("tmpId") == job_id
                                   for x in load_entries(default_path()))

                result = advance(entry, http, time.sleep, file_bytes,
                                 is_gone=_still_there)
                if result["status"] != "cancelled":
                    _persist(result)
                logger.info(f"代理任务结束: {result['tmpId']} -> {result['status']}")
        except Exception as e:  # noqa: BLE001 — 驱动线程绝不能死
            logger.error(f"代理任务驱动器异常: {e}")
        time.sleep(POLL_SECONDS)


def start_job_driver(upload_folder: str, port: int = 7860):
    """启动后台驱动线程；返回线程对象。"""
    code = os.environ.get("ACCESS_CODE", "")
    files_dir = os.path.join(upload_folder, "agent_uploads")
    os.makedirs(files_dir, exist_ok=True)
    t = threading.Thread(target=_loop,
                         args=(f"http://127.0.0.1:{port}", code, files_dir),
                         daemon=True)
    t.start()
    logger.info("已启动服务端代理任务驱动器")
    return t
