"""未被解析的 <tool_call> 不得进入报告正文。

LLM 偶尔会生成结尾畸形的工具调用 JSON（缺 }、多反引号、被 max_tokens
截断）。_parse_tool_calls 的正则要求 <tool_call>{...}</tool_call>，匹配
不上就静默返回空，于是「没有工具调用」的分支把整段原文当成章节内容返回，
标签原样写进成品报告（report_45f90f10d9e2 第四章即此）。

这里只做两件事：认出这类标记、把整块剪掉。判定用标记本身而不是 JSON
是否合法——因为正是 JSON 不合法时才需要它。
"""

import re

# 到闭合标签为止；没有闭合标签（被截断）就吃到结尾
_BLOCK = re.compile(r'<tool_call\b[^>]*>.*?(?:</tool_call\s*>|\Z)',
                    flags=re.DOTALL | re.IGNORECASE)
_ANY_TAG = re.compile(r'</?tool_call\b', flags=re.IGNORECASE)


def has_tool_call_markup(text: str) -> bool:
    """文本里是否残留工具调用标记（合法与畸形一律算）。"""
    return bool(text) and bool(_ANY_TAG.search(text))


def strip_tool_call_blocks(text: str) -> str:
    """剪掉整块工具调用，连同块内畸形 JSON；正常正文原样保留。"""
    if not text:
        return text
    return _BLOCK.sub('', text).strip()
