"""TDD: 畸形 <tool_call> 绝不能变成报告正文。

现象（report_45f90f10d9e2 第四章）：LLM 生成的工具调用 JSON 结尾畸形
（缺 } 且多一个反引号），_parse_tool_calls 的正则匹配不上 -> 解析为空 ->
「工具调用已足够」分支把整段原文当成章节最终内容返回，标签原样进了报告。
"""
from app.utils.tool_call_guard import has_tool_call_markup, strip_tool_call_blocks

MALFORMED = '''## 四、逐句修订建议：标题/正文/标签

<tool_call>
{"name": "interview_agents", "parameters": {"query": "请告诉我这篇笔记的完整正文"}`
</tool_call>'''


def test_detects_markup_even_when_the_json_is_malformed():
    assert has_tool_call_markup(MALFORMED) is True


def test_detects_an_unclosed_block():
    assert has_tool_call_markup('正文\n<tool_call>\n{"name": "x"') is True


def test_clean_prose_is_not_flagged():
    assert has_tool_call_markup("## 第四章\n\n正常的分析内容，提到 tool 也不算。") is False


def test_strips_the_whole_block_including_malformed_json():
    out = strip_tool_call_blocks(MALFORMED)
    assert "<tool_call>" not in out and "</tool_call>" not in out
    assert "interview_agents" not in out
    assert out.startswith("## 四、逐句修订建议")


def test_strips_an_unterminated_block_to_the_end():
    out = strip_tool_call_blocks('正文保留\n<tool_call>\n{"name": "x"')
    assert out == "正文保留"


def test_leaves_clean_content_untouched():
    text = "## 第四章\n\n第一句。第二句。"
    assert strip_tool_call_blocks(text) == text


def test_strips_multiple_blocks():
    out = strip_tool_call_blocks("A<tool_call>{}</tool_call>B<tool_call>{}</tool_call>C")
    assert "tool_call" not in out
    assert "A" in out and "B" in out and "C" in out


# ---- 集成：真实响应流经 ReportAgent 的最终答案路径 ----

def test_report_agent_imports_and_uses_the_guard():
    import inspect
    from app.services import report_agent as ra
    src = inspect.getsource(ra._ReportSectionMixin if hasattr(ra, "_ReportSectionMixin")
                            else ra)
    # 三处防线都在：解析失败告警、畸形退回重试、最终答案剪裁
    assert "工具调用 JSON 解析失败" in src
    assert "has_tool_call_markup(cleaned_response)" in src
    assert src.count("strip_tool_call_blocks(") >= 3


def test_malformed_call_is_not_parsed_as_a_tool_call():
    # 复现根因：结尾畸形 -> 正则匹配不上 -> 解析为空（这一步的行为不变）
    from app.services.report_agent import ReportAgent
    agent = ReportAgent.__new__(ReportAgent)
    calls = agent._parse_tool_calls(MALFORMED)
    assert calls == []
    # 但这段文本现在会被识别为「有工具调用意图」，因此不会变成正文
    assert has_tool_call_markup(MALFORMED) is True
