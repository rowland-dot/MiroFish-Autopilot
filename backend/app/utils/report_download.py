"""Build a downloadable payload for a report in a requested format.

Pure helper so the Flask /download route stays thin glue. 'docx' produces a
Word document from the report markdown; any other value (missing or unknown)
yields Markdown — the existing default behaviour.
"""

_DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
# Flask appends "; charset=utf-8" for text/* mimetypes — keep it bare here.
_MD_MIME = "text/markdown"


def _download_stem(report_id: str, source_filename) -> str:
    """人类可读的下载名主干：report_<原始文件名去扩展名>，无来源时回退 report_<id>。"""
    stem = str(source_filename or "").strip()
    if stem:
        # 去掉最后一个扩展名；替换路径/非法字符，保留中文
        if "." in stem:
            stem = stem.rsplit(".", 1)[0]
        for ch in '/\\:*?"<>|':
            stem = stem.replace(ch, "_")
        stem = stem.strip()
    if not stem:
        return report_id
    return f"report_{stem}"


def render_report_download(report, fmt, source_filename=None):
    """Return (data: bytes, download_name: str, mimetype: str) for the report.

    Args:
        report: object exposing .report_id and .markdown_content.
        fmt: requested format ("docx" or "md"/None/unknown).
        source_filename: 原始上传文件名（可选）——下载名将命名为
            report_<原文件名>.<格式>，缺失时回退为 report_<id>.<格式>。
    """
    stem = _download_stem(report.report_id, source_filename)
    if (fmt or "md").lower() == "docx":
        from .docx_export import markdown_to_docx_bytes
        return (
            markdown_to_docx_bytes(report.markdown_content),
            f"{stem}.docx",
            _DOCX_MIME,
        )
    return (
        report.markdown_content.encode("utf-8"),
        f"{stem}.md",
        _MD_MIME,
    )
