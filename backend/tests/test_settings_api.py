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


def test_get_settings_includes_active_model_and_deepseek_available(client):
    r = client.get('/api/settings').get_json()['data']
    assert r['active_model'] in ('minimax-m3', 'deepseek-v4-pro')
    assert isinstance(r['deepseek_available'], bool)


def test_deepseek_available_false_when_key_unset(client, monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    assert client.get('/api/settings').get_json()['data']['deepseek_available'] is False


def test_deepseek_available_true_when_key_set(client, monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'ds_key')
    assert client.get('/api/settings').get_json()['data']['deepseek_available'] is True


def test_post_active_model_valid(client):
    r = client.post('/api/settings', json={'active_model': 'deepseek-v4-pro'})
    assert r.get_json()['data']['active_model'] == 'deepseek-v4-pro'


def test_post_active_model_invalid_400(client):
    r = client.post('/api/settings', json={'active_model': 'gpt-9'})
    assert r.status_code == 400
