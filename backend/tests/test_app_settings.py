"""TDD: server-persisted app settings store + think-level semantics.

Spec: docs/specs/2026-07-16-think-level-toggle-spec.md
"""
import json

from app.utils.app_settings import get_setting, set_setting, get_think_level, THINK_LEVELS


def test_default_when_file_missing(tmp_path):
    path = tmp_path / "app_settings.json"
    assert get_setting("think_level", "economy", path=str(path)) == "economy"


def test_set_then_get_roundtrip(tmp_path):
    path = str(tmp_path / "app_settings.json")
    set_setting("think_level", "deep", path=path)
    assert get_setting("think_level", "economy", path=path) == "deep"


def test_corrupt_file_falls_back_to_default(tmp_path):
    p = tmp_path / "app_settings.json"
    p.write_text("{not json!!", encoding="utf-8")
    assert get_setting("think_level", "economy", path=str(p)) == "economy"
    # and a set repairs the file
    set_setting("think_level", "deep", path=str(p))
    assert json.loads(p.read_text(encoding="utf-8"))["think_level"] == "deep"


def test_set_preserves_other_keys(tmp_path):
    path = str(tmp_path / "app_settings.json")
    set_setting("other", "x", path=path)
    set_setting("think_level", "deep", path=path)
    assert get_setting("other", None, path=path) == "x"


def test_get_think_level_defaults_to_economy_and_sanitizes(tmp_path):
    path = str(tmp_path / "app_settings.json")
    assert get_think_level(path=path) == "economy"          # missing file
    set_setting("think_level", "garbage", path=path)
    assert get_think_level(path=path) == "economy"          # unknown value
    set_setting("think_level", "deep", path=path)
    assert get_think_level(path=path) == "deep"
    assert set(THINK_LEVELS) == {"economy", "deep"}
