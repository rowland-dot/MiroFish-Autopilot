"""TDD: finalize stale run_state records left by a restart.

A container restart kills the OASIS subprocess but never updates
run_state.json, so the record stays 'running' forever — the UI then shows a
phantom running job and the frontend driver polls a corpse.
"""
import json
import os

from app.utils.run_state_reconcile import finalize_status, reconcile_run_states


def _write(root, sim_id, state):
    d = os.path.join(root, sim_id)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "run_state.json"), "w", encoding="utf-8") as f:
        json.dump(state, f)
    return os.path.join(d, "run_state.json")


def _read(root, sim_id):
    with open(os.path.join(root, sim_id, "run_state.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def test_finalize_completed_when_all_rounds_done():
    assert finalize_status({"runner_status": "running", "current_round": 72,
                            "total_rounds": 72}) == "completed"


def test_finalize_stopped_when_rounds_incomplete():
    assert finalize_status({"runner_status": "running", "current_round": 39,
                            "total_rounds": 72}) == "stopped"


def test_finalize_leaves_terminal_states_alone():
    for s in ("completed", "stopped", "failed", "idle"):
        assert finalize_status({"runner_status": s}) is None


def test_reconcile_finalizes_only_non_terminal(tmp_path):
    root = str(tmp_path)
    _write(root, "sim_dead", {"runner_status": "running", "current_round": 39,
                              "total_rounds": 72, "twitter_running": True})
    _write(root, "sim_done", {"runner_status": "completed", "current_round": 72,
                              "total_rounds": 72})
    changed = reconcile_run_states(root)
    assert changed == ["sim_dead"]
    dead = _read(root, "sim_dead")
    assert dead["runner_status"] == "stopped"
    assert dead["twitter_running"] is False          # platform flags cleared
    assert _read(root, "sim_done")["runner_status"] == "completed"   # untouched


def test_reconcile_tolerates_missing_dir_and_corrupt_files(tmp_path):
    root = str(tmp_path / "nope")
    assert reconcile_run_states(root) == []          # missing dir -> no crash
    root2 = str(tmp_path)
    d = os.path.join(root2, "sim_bad")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "run_state.json"), "w", encoding="utf-8") as f:
        f.write("not json")
    assert reconcile_run_states(root2) == []         # corrupt -> skipped, no crash
