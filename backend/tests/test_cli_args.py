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


def test_report_accepts_report_id_instead_of_job_id():
    # 任务 done 后卡片会被 prune 掉，job_id 就查不到了；report_id 是稳定的取回路径
    ns = cli.parse_args(["report", "--report-id", "report_abc", "-o", "out.md"])
    assert ns.report_id == "report_abc"
    assert ns.job_id is None
    assert ns.output == "out.md"


def test_report_still_accepts_a_job_id_positionally():
    ns = cli.parse_args(["report", "tmp_1_0"])
    assert ns.job_id == "tmp_1_0"
    assert ns.report_id is None


def test_delete_subcommand_takes_a_job_id():
    ns = cli.parse_args(["delete", "tmp_1_0"])
    assert ns.command == "delete"
    assert ns.job_id == "tmp_1_0"
