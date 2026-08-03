"""TDD: 报告采访 toggle — when off, the ReACT agent never sees the tool."""
from app.services.report_agent import ReportAgent


def _tools(enabled, monkeypatch, tmp_path):
    import app.utils.app_settings as st
    p = str(tmp_path / "s.json")
    if enabled:
        st.set_setting("interviews_enabled", True, path=p)
    monkeypatch.setattr(st, "_DEFAULT_PATH", p)
    agent = ReportAgent.__new__(ReportAgent)   # no LLM/Zep init needed
    return agent._define_tools()


def test_interview_tool_hidden_when_disabled(monkeypatch, tmp_path):
    tools = _tools(False, monkeypatch, tmp_path)
    assert "interview_agents" not in tools
    assert "quick_search" in tools             # other tools untouched


def test_interview_tool_present_when_enabled(monkeypatch, tmp_path):
    tools = _tools(True, monkeypatch, tmp_path)
    assert "interview_agents" in tools
