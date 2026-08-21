"""启动时自动恢复：从 HF Dataset 拉回最新备份。

HF 会随时因宿主机维护重启 Space，磁盘是临时的——重启即清空。此前唯一的
恢复入口在部署脚本里，无人值守的重启会静默丢掉全部历史，直到有人发现。
夜间备份线程（backup_scheduler）已经把备份传到私有 HF Dataset；这里补上
另一半：容器启动时若数据目录为空，则自动拉最新备份恢复。

隔离模块（不改上游文件）；恢复失败绝不能阻断应用启动。
"""

import io
import os
import re

from ..utils.backup import restore_from_bytes
from ..utils.logger import logger

# 认调度器真实上传的名字（backups/mirofish-<ts>.tar.gz）以及部署脚本的
# 旧命名（mirofish-backup-<ts>.tar.gz）。时间戳在文件名里，按它排序而不是
# 按整条路径——否则不同目录会把顺序打乱。
_BACKUP_RE = re.compile(r"mirofish-(?:backup-)?(\d{8}-\d{6})\.tar\.gz$")


def _has_data(data_dir: str) -> bool:
    sims = os.path.join(data_dir, "simulations")
    try:
        return any(os.scandir(sims))
    except OSError:
        return False


def pick_newest(filenames) -> str:
    """按文件名里的时间戳选最新；非备份文件忽略。"""
    hits = []
    for f in (filenames or []):
        m = _BACKUP_RE.search(f or "")
        if m:
            hits.append((m.group(1), f))
    return max(hits)[1] if hits else None


def _hf_list(repo: str, token: str):
    from huggingface_hub import HfApi
    return HfApi(token=token).list_repo_files(repo_id=repo, repo_type="dataset")


def _hf_download(repo: str, token: str, name: str) -> bytes:
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(repo_id=repo, repo_type="dataset", filename=name, token=token)
    with io.open(path, "rb") as f:
        return f.read()


def restore_latest_if_empty(data_dir: str, repo: str, token: str,
                            lister=_hf_list, downloader=_hf_download) -> bool:
    """数据目录为空且配置齐全时恢复最新备份。永不抛异常。"""
    try:
        if not repo or not token:
            return False
        if _has_data(data_dir):
            return False               # 有数据绝不覆盖
        newest = pick_newest(lister(repo, token))
        if not newest:
            # 静默返回 False 曾让「命名不匹配」的失效状态潜伏了 11 天，
            # 直到一次 HF 重启把数据清空才暴露。必须留痕。
            logger.error(f"启动恢复：数据目录为空，但备份库 {repo} 里没有可用备份")
            return False
        archive = downloader(repo, token, newest)
        if not archive:
            return False
        n = restore_from_bytes(archive, data_dir)
        if n == 0:
            logger.warning(f"启动恢复：备份 {newest} 是空档案，未恢复任何内容")
            return False
        logger.warning(f"启动恢复：数据目录为空，已从 {newest} 恢复 {n} 项（HF 重启会清空临时磁盘）")
        return True
    except Exception as e:             # noqa: BLE001 — 恢复失败不能拖垮启动
        logger.error(f"启动恢复失败（应用继续启动）: {e}")
        return False
