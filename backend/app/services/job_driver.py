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
TERMINAL_STATUSES = ("done", "failed", "cancelled")


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
        # 登录失败绝不能标记「已登录」：那会让之后每个请求都 401，
        # 直到进程重启为止（口令写错时整条无头链路永久瘫痪）
        if self._logged_in or not self.code:
            return
        try:
            resp = self.session.post(f"{self.base}/api/auth/login",
                                     json={"code": self.code}, timeout=30)
            if 200 <= getattr(resp, "status_code", 0) < 300:
                self._logged_in = True
            else:
                logger.warning(f"代理驱动器登录失败: HTTP {resp.status_code}，下次重试")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"代理驱动器登录异常: {e}，下次重试")

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


def cleanup_upload(files_dir: str, job_id: str):
    """任务终态后删除上传字节；幂等。不清理会无限占用容器磁盘。"""
    try:
        os.remove(os.path.join(files_dir, f"{job_id}.bin"))
    except OSError:
        pass


def run_once(files_dir: str, http):
    """推进一个代理任务（如果有）。抽出来便于测试，不含循环与 sleep。"""
    entry = pick_next(load_entries(default_path()))
    if not entry:
        return None

    job_id = entry["tmpId"]
    path = os.path.join(files_dir, f"{job_id}.bin")
    try:
        with open(path, "rb") as f:
            file_bytes = f.read()
    except OSError:
        # 文件丢失（如恢复未覆盖 agent_uploads）：必须显式失败，
        # 否则任务永远卡在 queued、error 为空，还占死一个槽位
        failed = {**entry, "status": "failed",
                  "error": "上传文件内容丢失，请重新提交任务（agent upload missing）"}
        _persist(failed)
        cleanup_upload(files_dir, job_id)
        logger.error(f"代理任务上传丢失: {job_id}")
        return failed

    if entry["status"] == "queued":
        entry = {**entry, "status": "ontology"}
        _persist(entry)

    def _is_gone(jid=job_id):
        """条目已被删除（用户取消）——驱动器必须停手。"""
        return not any(x.get("tmpId") == jid
                       for x in load_entries(default_path()))

    def _on_change(snapshot):
        # 每个阶段/ID 变化立刻落盘：状态查询实时可见，重启可从真实进度续跑
        if not _is_gone():
            _persist(snapshot)

    result = advance(entry, http, time.sleep, file_bytes,
                     is_gone=_is_gone, on_change=_on_change)
    if result["status"] != "cancelled":
        _persist(result)
    if result["status"] in TERMINAL_STATUSES:
        cleanup_upload(files_dir, job_id)
    logger.info(f"代理任务结束: {job_id} -> {result['status']}")
    return result


def _loop(base_url: str, access_code: str, files_dir: str):
    http = LocalHttp(base_url, access_code)
    while True:
        try:
            run_once(files_dir, http)
        except Exception as e:  # noqa: BLE001 — 驱动线程绝不能死
            logger.error(f"代理任务驱动器异常: {e}")
        time.sleep(POLL_SECONDS)


def start_job_driver(upload_folder: str, port: int = 7860):
    """启动后台驱动线程；返回线程对象（reloader 父进程下不启动）。"""
    code = os.environ.get("ACCESS_CODE", "")
    files_dir = os.path.join(upload_folder, "agent_uploads")
    os.makedirs(files_dir, exist_ok=True)
    t = threading.Thread(target=_loop,
                         args=(f"http://127.0.0.1:{port}", code, files_dir),
                         daemon=True)
    t.start()
    logger.info("已启动服务端代理任务驱动器")
    return t
