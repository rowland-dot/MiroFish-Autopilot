"""Build a downloadable payload for a report in a requested format.

Pure helper so the Flask /download route stays thin glue. 'docx' produces a
Word document from the report markdown; any other value (missing or unknown)
yields Markdown — the existing default behaviour.
"""

_DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_MD_MIME = "text/markdown; charset=utf-8"


def render_report_download(report, fmt):
    """Return (data: bytes, download_name: str, mimetype: str) for the report.

    Args:
        report: object exposing .report_id and .markdown_content.
        fmt: requested format ("docx" or "md"/None/unknown).
    """
    report_id = report.report_id
    if (fmt or "md").lower() == "docx":
        from .docx_export import markdown_to_docx_bytes
        return (
            markdown_to_docx_bytes(report.markdown_content),
            f"{report_id}.docx",
            _DOCX_MIME,
        )
    return (
        report.markdown_content.encode("utf-8"),
        f"{report_id}.md",
        _MD_MIME,
    )
