"""TDD: CLI argument surface (network paths are exercised live, not here)."""
import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "mirofish_cli",
    pathlib.Path(__file__).resolve().parents[2] / "cli" / "mirofish.py",
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def test_submit_requires_file_and_prompt():
    ns = cli.parse_args(["submit", "--file", "a.docx", "--prompt", "p"])
    assert ns.command == "submit"
    assert ns.file == "a.docx"
    assert ns.prompt == "p"


def test_status_takes_a_job_id():
    ns = cli.parse_args(["status", "tmp_1_0"])
    assert ns.command == "status"
    assert ns.job_id == "tmp_1_0"


def test_report_supports_output_path():
    ns = cli.parse_args(["report", "tmp_1_0", "-o", "out.md"])
    assert ns.command == "report"
    assert ns.output == "out.md"


def test_base_url_defaults_to_the_space(monkeypatch):
    monkeypatch.delenv("MIROFISH_URL", raising=False)
    ns = cli.parse_args(["status", "j"])
    assert "hf.space" in ns.url
