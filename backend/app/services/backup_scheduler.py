"""每日自动备份到私有 HF Dataset。

仅当同时配置了 BACKUP_HF_REPO + HF_TOKEN 时启动后台线程（本地开发默认关闭）。
线程每小时检查一次，距上次备份 >=24h 则打包整个数据目录上传到 Dataset。
huggingface_hub 采用惰性导入——未配置时无需该依赖。

Spec: docs/specs/2026-07-23-backup-restore-spec.md
"""

import os
import threading
import time
from datetime import datetime

from ..utils.backup import make_backup_bytes, should_backup
from ..utils.logger import logger


def _hf_upload(archive: bytes, repo: str, token: str, path: str) -> None:
    """真实上传实现（惰性导入 huggingface_hub）。"""
    from huggingface_hub import HfApi
    api = HfApi()
    api.upload_file(
        path_or_fileobj=archive,
        path_in_repo=path,
        repo_id=repo,
        repo_type="dataset",
        token=token,
        commit_message=f"backup {path}",
    )


def run_backup_once(data_dir, repo, token, state_path, now=None, upload=_hf_upload) -> bool:
    """距上次备份满 24h 则执行一次备份上传；否则跳过。返回是否执行。"""
    now = now or datetime.now()
    last = None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            last = f.read().strip()
    except OSError:
        last = None
    if not should_backup(last, now):
        return False

    archive = make_backup_bytes(data_dir)
    path = f"backups/mirofish-{now.strftime('%Y%m%d-%H%M%S')}.tar.gz"
    upload(archive, repo, token, path)
    with open(state_path, "w", encoding="utf-8") as f:
        f.write(now.isoformat())
    return True


def _loop(data_dir, repo, token, state_path):
    while True:
        try:
            if run_backup_once(data_dir, repo, token, state_path):
                logger.info("每日自动备份已上传到 HF Dataset")
        except Exception as e:  # 备份失败绝不能拖垮主服务
            logger.error(f"自动备份失败: {e}")
        time.sleep(3600)  # 每小时检查一次


def start_backup_scheduler(data_dir: str):
    """配置齐全则启动后台备份线程；否则返回 None（不启动）。"""
    repo = os.environ.get("BACKUP_HF_REPO")
    token = os.environ.get("HF_TOKEN")
    if not repo or not token:
        return None
    state_path = os.path.join(data_dir, ".last_backup")
    t = threading.Thread(
        target=_loop, args=(data_dir, repo, token, state_path), daemon=True
    )
    t.start()
    logger.info("已启动每日自动备份线程（目标 HF Dataset: %s）", repo)
    return t
