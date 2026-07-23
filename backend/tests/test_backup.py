"""TDD: backup/restore archive helpers.

Spec: docs/specs/2026-07-23-backup-restore-spec.md
"""
import io
import os
import tarfile
from datetime import datetime, timedelta

import pytest

from app.utils.backup import make_backup_bytes, restore_from_bytes, should_backup


def _seed(root):
    os.makedirs(os.path.join(root, "projects"), exist_ok=True)
    os.makedirs(os.path.join(root, "reports"), exist_ok=True)
    with open(os.path.join(root, "app_settings.json"), "w", encoding="utf-8") as f:
        f.write('{"think_level":"deep"}')
    with open(os.path.join(root, "projects", "p1.json"), "w", encoding="utf-8") as f:
        f.write("项目一")  # non-ascii content survives round-trip


def test_backup_bytes_is_a_gzip_tar(tmp_path):
    _seed(str(tmp_path))
    data = make_backup_bytes(str(tmp_path))
    assert data[:2] == b"\x1f\x8b"  # gzip magic
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        names = tar.getnames()
    assert any(n.endswith("app_settings.json") for n in names)
    assert any(n.endswith("projects/p1.json") for n in names)


def test_round_trip_is_identity(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir(); dst.mkdir()
    _seed(str(src))
    data = make_backup_bytes(str(src))

    count = restore_from_bytes(data, str(dst))
    assert count >= 2  # at least the two files
    assert (dst / "app_settings.json").read_text(encoding="utf-8") == '{"think_level":"deep"}'
    assert (dst / "projects" / "p1.json").read_text(encoding="utf-8") == "项目一"


def test_restore_overwrites_existing(tmp_path):
    src = tmp_path / "src"; dst = tmp_path / "dst"
    src.mkdir(); dst.mkdir()
    _seed(str(src))
    (dst / "app_settings.json").write_text("STALE", encoding="utf-8")
    restore_from_bytes(make_backup_bytes(str(src)), str(dst))
    assert (dst / "app_settings.json").read_text(encoding="utf-8") == '{"think_level":"deep"}'


def test_restore_rejects_path_traversal(tmp_path):
    # craft a malicious archive with a ../ member
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        payload = b"pwned"
        info = tarfile.TarInfo(name="../evil.txt")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    dst = tmp_path / "dst"; dst.mkdir()
    with pytest.raises(ValueError):
        restore_from_bytes(buf.getvalue(), str(dst))
    assert not (tmp_path / "evil.txt").exists()  # escape did not happen


def test_should_backup_cadence():
    now = datetime(2026, 7, 23, 12, 0, 0)
    assert should_backup(None, now) is True                                  # never backed up
    assert should_backup((now - timedelta(hours=25)).isoformat(), now) is True
    assert should_backup((now - timedelta(hours=5)).isoformat(), now) is False
    assert should_backup("garbage", now) is True                              # unparseable -> back up
