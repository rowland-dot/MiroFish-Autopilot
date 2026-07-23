"""TDD: /api/backup and /api/restore endpoints (gated, round-trip).

Spec: docs/specs/2026-07-23-backup-restore-spec.md
"""
import io

import pytest
from flask import Flask

from app.api.backup import backup_bp
from app.auth import init_auth


def make_client(tmp_path, **config):
    data_dir = tmp_path / "uploads"
    (data_dir / "projects").mkdir(parents=True)
    (data_dir / "app_settings.json").write_text('{"think_level":"economy"}', encoding="utf-8")
    (data_dir / "projects" / "p.json").write_text("proj", encoding="utf-8")

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "t"
    app.config["AUTH_FAIL_DELAY"] = 0
    app.config["UPLOAD_FOLDER"] = str(data_dir)
    app.config.update(config)
    init_auth(app)
    app.register_blueprint(backup_bp, url_prefix="/api")
    return app.test_client(), data_dir


def test_backup_returns_gzip_attachment(tmp_path):
    c, _ = make_client(tmp_path)
    r = c.get("/api/backup")
    assert r.status_code == 200
    assert r.data[:2] == b"\x1f\x8b"  # gzip
    assert "attachment" in r.headers.get("Content-Disposition", "")


def test_restore_round_trip(tmp_path):
    c, data_dir = make_client(tmp_path)
    archive = c.get("/api/backup").data

    # wipe the live data
    (data_dir / "app_settings.json").unlink()
    (data_dir / "projects" / "p.json").unlink()

    r = c.post("/api/restore", data={"archive": (io.BytesIO(archive), "b.tar.gz")},
               content_type="multipart/form-data")
    assert r.status_code == 200 and r.get_json()["success"] is True
    assert (data_dir / "app_settings.json").read_text(encoding="utf-8") == '{"think_level":"economy"}'
    assert (data_dir / "projects" / "p.json").read_text(encoding="utf-8") == "proj"


def test_restore_without_file_is_400(tmp_path):
    c, _ = make_client(tmp_path)
    assert c.post("/api/restore").status_code == 400


def test_endpoints_gated_when_auth_enabled(tmp_path):
    c, _ = make_client(tmp_path, AUTH_ENABLED=True, ACCESS_CODE="s3cret")
    assert c.get("/api/backup").status_code == 401
    assert c.post("/api/restore").status_code == 401
