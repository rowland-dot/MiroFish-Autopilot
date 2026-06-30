"""TDD: the upload endpoint gate (Config.ALLOWED_EXTENSIONS) accepts .docx.

graph.py:allowed_file() checks the uploaded filename's extension against
Config.ALLOWED_EXTENSIONS before the file is saved/parsed. .docx must pass;
.pdf must keep passing.
"""
from app.config import Config


def test_docx_is_an_allowed_upload_extension():
    assert "docx" in Config.ALLOWED_EXTENSIONS


def test_pdf_remains_allowed():
    assert "pdf" in Config.ALLOWED_EXTENSIONS
