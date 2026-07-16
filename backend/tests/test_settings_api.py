"""TDD: GET/POST /api/settings (think level).

Spec: docs/specs/2026-07-16-think-level-toggle-spec.md
"""
import pytest
from flask import Flask

import app.utils.app_settings as app_settings
from app.api.settings import settings_bp


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "_DEFAULT_PATH", str(tmp_path / "app_settings.json"))
    app = Flask(__name__)
    app.register_blueprint(settings_bp, url_prefix="/api/settings")
    return app.test_client()


def test_get_returns_default_economy(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.get_json()["data"]["think_level"] == "economy"


def test_post_persists_deep_then_get_reflects_it(client):
    r = client.post("/api/settings", json={"think_level": "deep"})
    assert r.status_code == 200
    assert r.get_json()["success"] is True
    assert client.get("/api/settings").get_json()["data"]["think_level"] == "deep"


def test_post_rejects_invalid_value(client):
    r = client.post("/api/settings", json={"think_level": "ultra"})
    assert r.status_code == 400
    # and the stored value is untouched
    assert client.get("/api/settings").get_json()["data"]["think_level"] == "economy"
