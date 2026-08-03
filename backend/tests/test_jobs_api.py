"""TDD: headless REST surface — spec contracts B1/B2/B3."""
import io

import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_FOLDER", str(tmp_path))
    from app.config import Config
    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _submit(client, prompt="预测舆情", name="r.docx"):
    data = {"prompt": prompt, "file": (io.BytesIO(b"doc bytes"), name)}
    return client.post("/api/jobs", data=data, content_type="multipart/form-data")


def test_submit_returns_job_id_and_queued(client):
    res = _submit(client)
    assert res.status_code == 200
    body = res.get_json()["data"]
    assert body["job_id"].startswith("tmp_")
    assert body["status"] == "queued"


def test_submit_requires_file_and_prompt(client):
    res = client.post("/api/jobs", data={"prompt": "x"},
                      content_type="multipart/form-data")
    assert res.status_code == 400


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
