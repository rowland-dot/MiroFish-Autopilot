"""TDD: build the report download payload for a requested format.

Pure helper consumed by the /download route: given a report and a format,
return (bytes, download_name, mimetype). 'docx' -> Word; anything else
(missing/unknown) -> Markdown (the existing default).
"""
from types import SimpleNamespace

from app.utils.report_download import render_report_download


def _report():
    return SimpleNamespace(report_id="report_x", markdown_content="# Title\n\nbody 中文")


def test_docx_payload_is_a_docx_named_for_the_report():
    data, name, mime = render_report_download(_report(), "docx")
    assert data[:2] == b"PK"  # docx is a zip
    assert name == "report_x.docx"
    assert "wordprocessingml" in mime


def test_md_is_the_default_when_format_missing():
    data, name, mime = render_report_download(_report(), None)
    assert data.decode("utf-8") == "# Title\n\nbody 中文"
    assert name == "report_x.md"
    assert "markdown" in mime


def test_unknown_format_falls_back_to_md():
    _, name, _ = render_report_download(_report(), "pdf")
    assert name.endswith(".md")


def test_download_named_after_source_file_with_report_prefix():
    # 上传 爆款详情页.docx → 下载 report_爆款详情页.docx / .md
    _, name, _ = render_report_download(_report(), "docx", source_filename="爆款详情页.docx")
    assert name == "report_爆款详情页.docx"
    _, name_md, _ = render_report_download(_report(), "md", source_filename="爆款详情页.docx")
    assert name_md == "report_爆款详情页.md"


def test_source_extension_stripped_and_path_chars_sanitized():
    _, name, _ = render_report_download(_report(), "docx", source_filename="a/b\\c: brief.v2.pdf")
    assert name == "report_a_b_c_ brief.v2.docx"  # path/colon chars replaced, last ext stripped


def test_blank_or_missing_source_falls_back_to_report_id():
    _, name, _ = render_report_download(_report(), "docx", source_filename="   ")
    assert name == "report_x.docx"
    _, name2, _ = render_report_download(_report(), "docx", source_filename=None)
    assert name2 == "report_x.docx"
