"""TDD: auto-restore at boot.

HF restarts Spaces at will; the disk is ephemeral and the restore
safety-net only ran during deploys -- an unattended restart silently wiped
all history until a human noticed (2026-07-31). At boot, an empty data dir
pulls the newest backup from the same HF dataset the nightly scheduler
uploads to.
"""
import os

from app.services.boot_restore import pick_newest, restore_latest_if_empty
from app.utils.backup import make_backup_bytes


def _seed(data_dir):
    d = data_dir / "simulations" / "sim_1"
    d.mkdir(parents=True)
    (d / "run_state.json").write_text('{"runner_status": "completed"}', encoding="utf-8")


def test_pick_newest_by_timestamp_name():
    files = ["mirofish-backup-20260729-010000.tar.gz",
             "mirofish-backup-20260731-013434.tar.gz",
             "mirofish-backup-20260730-204721.tar.gz",
             "README.md"]
    assert pick_newest(files) == "mirofish-backup-20260731-013434.tar.gz"
    assert pick_newest(["README.md"]) is None
    assert pick_newest([]) is None


def test_restores_into_empty_data_dir(tmp_path):
    src = tmp_path / "src"; _seed(src)
    archive = make_backup_bytes(str(src))
    dst = tmp_path / "dst"; dst.mkdir()
    ok = restore_latest_if_empty(
        str(dst), repo="r", token="t",
        lister=lambda repo, token: ["mirofish-backup-20260731-013434.tar.gz"],
        downloader=lambda repo, token, name: archive,
    )
    assert ok is True
    assert (dst / "simulations" / "sim_1" / "run_state.json").exists()


def test_never_clobbers_existing_data(tmp_path):
    dst = tmp_path / "dst"; _seed(dst)
    calls = []
    ok = restore_latest_if_empty(
        str(dst), repo="r", token="t",
        lister=lambda *a: calls.append("list"),
        downloader=lambda *a: calls.append("dl"),
    )
    assert ok is False
    assert calls == []          # data present: no network touched


def test_missing_config_or_no_backups_is_a_quiet_noop(tmp_path):
    dst = tmp_path / "dst"; dst.mkdir()
    assert restore_latest_if_empty(str(dst), repo=None, token="t") is False
    assert restore_latest_if_empty(str(dst), repo="r", token=None) is False
    assert restore_latest_if_empty(
        str(dst), repo="r", token="t",
        lister=lambda *a: [], downloader=lambda *a: b"") is False


def test_download_failure_never_raises(tmp_path):
    dst = tmp_path / "dst"; dst.mkdir()
    def boom(*a): raise RuntimeError("hf down")
    assert restore_latest_if_empty(str(dst), repo="r", token="t",
                                   lister=boom, downloader=boom) is False


def test_pick_newest_matches_the_scheduler_actual_filenames():
    # 真实事故（2026-08-14）：调度器上传 backups/mirofish-<ts>.tar.gz，
    # 而这里只认 mirofish-backup-<ts>.tar.gz —— 永不匹配，自动恢复形同虚设。
    files = [
        "backups/mirofish-20260812-073158.tar.gz",
        "backups/mirofish-20260814-073245.tar.gz",
        "backups/mirofish-20260813-073222.tar.gz",
        ".gitattributes",
        "README.md",
    ]
    assert pick_newest(files) == "backups/mirofish-20260814-073245.tar.gz"


def test_pick_newest_still_matches_the_legacy_deploy_naming():
    files = ["mirofish-backup-20260805-005856.tar.gz",
             "mirofish-backup-20260812-032609.tar.gz"]
    assert pick_newest(files) == "mirofish-backup-20260812-032609.tar.gz"


def test_pick_newest_orders_by_timestamp_not_path():
    files = ["zz/mirofish-20260101-000000.tar.gz",
             "aa/mirofish-20260814-073245.tar.gz"]
    assert pick_newest(files) == "aa/mirofish-20260814-073245.tar.gz"


def test_pick_newest_ignores_non_backups():
    assert pick_newest(["README.md", "backups/notes.txt"]) is None
