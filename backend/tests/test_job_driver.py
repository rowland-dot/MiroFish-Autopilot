"""TDD: which agent entry the server driver picks, and when it stays idle."""
from app.services.job_driver import pick_next


def test_prefers_an_already_active_agent_entry():
    entries = [
        {"tmpId": "a", "mode": "agent", "status": "preparing"},
        {"tmpId": "b", "mode": "agent", "status": "queued"},
    ]
    assert pick_next(entries)["tmpId"] == "a"


def test_promotes_a_queued_agent_entry_when_nothing_is_active():
    entries = [
        {"tmpId": "old", "mode": "agent", "status": "done"},
        {"tmpId": "b", "mode": "agent", "status": "queued"},
    ]
    assert pick_next(entries)["tmpId"] == "b"


def test_never_touches_browser_entries():
    entries = [
        {"tmpId": "auto1", "mode": "auto", "status": "queued"},
        {"tmpId": "man1", "mode": "manual", "status": "running"},
    ]
    assert pick_next(entries) is None


def test_waits_while_a_browser_job_holds_the_slot():
    # 容量共享：浏览器任务占着运行槽时，代理任务必须排队等待
    entries = [
        {"tmpId": "auto1", "mode": "auto", "status": "running"},
        {"tmpId": "b", "mode": "agent", "status": "queued"},
    ]
    assert pick_next(entries) is None


def test_ignores_terminal_agent_entries():
    entries = [
        {"tmpId": "a", "mode": "agent", "status": "done"},
        {"tmpId": "b", "mode": "agent", "status": "failed"},
    ]
    assert pick_next(entries) is None
