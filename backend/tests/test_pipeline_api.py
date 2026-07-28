"""TDD: GET/POST/DELETE /api/pipeline."""
import pytest
from flask import Flask

import app.utils.pipeline_state as ps
from app.api.pipeline import pipeline_bp


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_DEFAULT_PATH", str(tmp_path / "pipeline_state.json"))
    app = Flask(__name__)
    app.register_blueprint(pipeline_bp, url_prefix="/api/pipeline")
    return app.test_client()


def test_get_empty(client):
    r = client.get("/api/pipeline")
    assert r.status_code == 200 and r.get_json()["data"]["entries"] == []


def test_post_then_get(client):
    client.post("/api/pipeline", json={"tmpId": "a", "status": "queued", "prompt": "p"})
    entries = client.get("/api/pipeline").get_json()["data"]["entries"]
    assert [e["tmpId"] for e in entries] == ["a"]


def test_post_upserts_not_duplicates(client):
    client.post("/api/pipeline", json={"tmpId": "a", "status": "queued"})
    r = client.post("/api/pipeline", json={"tmpId": "a", "status": "running"})
    entries = r.get_json()["data"]["entries"]
    assert len(entries) == 1 and entries[0]["status"] == "running"


def test_post_requires_tmpid(client):
    assert client.post("/api/pipeline", json={"status": "queued"}).status_code == 400


def test_delete_removes(client):
    client.post("/api/pipeline", json={"tmpId": "a", "status": "queued"})
    r = client.delete("/api/pipeline/a")
    assert r.status_code == 200 and r.get_json()["data"]["entries"] == []


def test_delete_unknown_id_is_ok(client):
    assert client.delete("/api/pipeline/nope").status_code == 200   # idempotent ack


def test_get_prunes_and_persists(client):
    client.post("/api/pipeline", json={"tmpId": "d", "status": "done"})
    assert client.get("/api/pipeline").get_json()["data"]["entries"] == []
    assert ps.load_entries(ps._DEFAULT_PATH) == []      # prune was persisted
