"""TDD: headless REST surface — spec contracts B1/B2/B3.

Isolation follows test_pipeline_api.py: patch pipeline_state._DEFAULT_PATH and
Config.UPLOAD_FOLDER at tmp_path, and mount only the jobs blueprint — the tests
must never read or write the live pipeline state.
"""
import io

import pytest
from flask import Flask

from app.api.jobs import jobs_bp
from app.config import Config
from app.utils import pipeline_state as ps


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_DEFAULT_PATH", str(tmp_path / "pipeline_state.json"))
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    app = Flask(__name__)
    app.register_blueprint(jobs_bp, url_prefix="/api/jobs")
    app.config["TESTING"] = True
    return app.test_client()


def _submit(client, prompt="预测舆情", name="r.docx"):
    data = {"prompt": prompt, "file": (io.BytesIO(b"doc bytes"), name)}
    return client.post("/api/jobs", data=data, content_type="multipart/form-data")


def test_submit_returns_job_id_and_queued(client):
    res = _submit(client)
    assert res.status_code == 200
    body = res.get_json()["data"]
    assert body["job_id"].startswith("tmp_")
    assert body["status"] == "queued"


def test_submit_persists_the_uploaded_bytes_for_the_driver(client, tmp_path):
    jid = _submit(client).get_json()["data"]["job_id"]
    saved = tmp_path / "agent_uploads" / f"{jid}.bin"
    assert saved.exists()
    assert saved.read_bytes() == b"doc bytes"


def test_submit_requires_file_and_prompt(client):
    res = client.post("/api/jobs", data={"prompt": "x"},
                      content_type="multipart/form-data")
    assert res.status_code == 400


def test_submit_rejected_when_queue_is_full(client):
    # 1 运行 + 2 排队 = 满；容量与浏览器任务共享
    for _ in range(3):
        assert _submit(client).status_code == 200
    res = _submit(client)
    assert res.status_code == 429
    assert res.get_json()["data"]["error"] == "queue full"


def test_status_of_unknown_job_is_404(client):
    assert client.get("/api/jobs/tmp_nope").status_code == 404


def test_status_reports_stage(client):
    jid = _submit(client).get_json()["data"]["job_id"]
    body = client.get(f"/api/jobs/{jid}").get_json()["data"]
    assert body["job_id"] == jid
    assert body["stage"] == "queued"


def test_report_before_completion_is_409(client):
    jid = _submit(client).get_json()["data"]["job_id"]
    res = client.get(f"/api/jobs/{jid}/report")
    assert res.status_code == 409
    assert res.get_json()["data"]["status"] == "queued"
