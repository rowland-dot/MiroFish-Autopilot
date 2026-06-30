"""File-to-Markdown conversion via markitdown.

Single entry point that turns a source document (.docx and the other office /
pdf formats markitdown supports) into Markdown, which the existing GraphRAG
text pipeline then consumes unchanged.
"""

from markitdown import MarkItDown

_converter = None


def _get_converter() -> MarkItDown:
    """Lazily construct and reuse a single MarkItDown instance."""
    global _converter
    if _converter is None:
        _converter = MarkItDown()
    return _converter


def convert_to_markdown(file_path: str) -> str:
    """Convert a document file to Markdown text.

    Args:
        file_path: path to the source file (.docx, .pdf, .pptx, .xlsx, …).

    Returns:
        The document's content as Markdown.
    """
    result = _get_converter().convert(file_path)
    return result.text_content
