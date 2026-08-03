"""TDD: agent job entries reuse the pipeline store's shape and capacity."""
from datetime import datetime

from app.services.job_store import (
    new_job_id, make_agent_entry, capacity_state, is_full,
)

NOW = datetime(2026, 8, 4, 12, 0, 0)


def test_job_id_is_pipeline_shaped():
    jid = new_job_id(NOW, 3)
    assert jid.startswith("tmp_")
    assert jid.endswith("_3")


def test_agent_entry_marks_mode_agent_and_starts_queued():
    e = make_agent_entry("tmp_1_0", "预测舆情走向", "report.docx", NOW)
    assert e["mode"] == "agent"          # never 'auto' — that is the browser driver's marker
    assert e["status"] == "queued"
    assert e["prompt"] == "预测舆情走向"
    assert e["fileName"] == "report.docx"
    assert e["tmpId"] == "tmp_1_0"
    assert e["createdAt"] == NOW.isoformat()


def test_capacity_counts_active_and_queued():
    entries = [
        {"tmpId": "a", "status": "running"},
        {"tmpId": "b", "status": "queued"},
        {"tmpId": "c", "status": "done"},
    ]
    assert capacity_state(entries) == (1, 1)
    assert is_full(entries) is False


def test_full_at_one_running_plus_two_queued():
    entries = [
        {"tmpId": "a", "status": "preparing"},
        {"tmpId": "b", "status": "queued"},
        {"tmpId": "c", "status": "queued"},
    ]
    assert capacity_state(entries) == (1, 2)
    assert is_full(entries) is True
