"""Backup/restore of the MiroFish data directory (backend/uploads/).

make_backup_bytes  → gzip-tar of the whole data tree, in memory.
restore_from_bytes → extract a gzip-tar back into the data dir, rejecting any
                     member that would escape the target (path traversal).
should_backup      → daily-cadence decision for the nightly self-backup.

Spec: docs/specs/2026-07-23-backup-restore-spec.md
"""

import io
import os
import tarfile
from datetime import datetime


def make_backup_bytes(data_dir: str) -> bytes:
    """Return a gzip-tar of everything under data_dir (arcnames relative)."""
    data_dir = os.path.abspath(data_dir)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        if os.path.isdir(data_dir):
            tar.add(data_dir, arcname=".")
    return buf.getvalue()


def _is_within(base: str, target: str) -> bool:
    base = os.path.abspath(base)
    target = os.path.abspath(target)
    return target == base or target.startswith(base + os.sep)


def restore_from_bytes(archive: bytes, data_dir: str) -> int:
    """Extract archive into data_dir, overwriting existing files.

    Rejects (raises ValueError) any member whose path escapes data_dir, before
    writing anything. Returns the number of regular files restored.
    """
    data_dir = os.path.abspath(data_dir)
    os.makedirs(data_dir, exist_ok=True)

    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        members = tar.getmembers()
        # Safety pass first — never write if any member is unsafe.
        for m in members:
            dest = os.path.join(data_dir, m.name)
            if not _is_within(data_dir, dest) or m.name.startswith("/") or ".." in m.name.split("/"):
                raise ValueError(f"unsafe archive member: {m.name}")
            if m.issym() or m.islnk():
                raise ValueError(f"link member not allowed: {m.name}")
        tar.extractall(data_dir)
        return sum(1 for m in members if m.isfile())


def should_backup(last_iso, now: datetime, min_interval_hours: int = 24) -> bool:
    """True if a backup is due (never done, unparseable, or >= interval old)."""
    if not last_iso:
        return True
    try:
        last = datetime.fromisoformat(last_iso)
    except (ValueError, TypeError):
        return True
    return (now - last).total_seconds() >= min_interval_hours * 3600
