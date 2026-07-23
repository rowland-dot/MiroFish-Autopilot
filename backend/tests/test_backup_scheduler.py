"""TDD: nightly self-backup scheduler (env-gated, HF upload).

Spec: docs/specs/2026-07-23-backup-restore-spec.md
"""
import os
from datetime import datetime, timedelta

from app.services.backup_scheduler import run_backup_once, start_backup_scheduler


def _seed(root):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "app_settings.json"), "w", encoding="utf-8") as f:
        f.write("{}")


def test_scheduler_is_noop_without_env(tmp_path, monkeypatch):
    monkeypatch.delenv("BACKUP_HF_REPO", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert start_backup_scheduler(str(tmp_path)) is None  # no thread started


def test_run_backup_once_fires_when_due_and_uploads(tmp_path):
    data = tmp_path / "uploads"; _seed(str(data))
    state = tmp_path / ".last_backup"
    calls = []

    def fake_upload(archive, repo, token, path):
        calls.append({"repo": repo, "token": token, "path": path, "size": len(archive)})

    did = run_backup_once(str(data), "me/backups", "hf_tok", str(state),
                          now=datetime(2026, 7, 23, 12, 0, 0), upload=fake_upload)
    assert did is True
    assert len(calls) == 1
    assert calls[0]["repo"] == "me/backups" and calls[0]["token"] == "hf_tok"
    assert calls[0]["size"] > 0
    assert state.exists()  # timestamp recorded


def test_run_backup_once_skips_when_recent(tmp_path):
    data = tmp_path / "uploads"; _seed(str(data))
    state = tmp_path / ".last_backup"
    now = datetime(2026, 7, 23, 12, 0, 0)
    state.write_text((now - timedelta(hours=2)).isoformat(), encoding="utf-8")
    calls = []
    did = run_backup_once(str(data), "me/backups", "hf_tok", str(state),
                          now=now, upload=lambda *a, **k: calls.append(1))
    assert did is False
    assert calls == []  # not uploaded
