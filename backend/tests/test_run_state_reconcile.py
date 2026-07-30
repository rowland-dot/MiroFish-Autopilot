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


def test_reconcile_also_fixes_manager_state_json(tmp_path):
    # SimulationManager persists its own state.json; a restart leaves it
    # 'running' too, which is why /api/simulation/list kept lying.
    root = str(tmp_path)
    d = os.path.join(root, "sim_x")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "run_state.json"), "w", encoding="utf-8") as f:
        json.dump({"runner_status": "running", "current_round": 5, "total_rounds": 72}, f)
    with open(os.path.join(d, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"simulation_id": "sim_x", "status": "running"}, f)

    reconcile_run_states(root)

    with open(os.path.join(d, "state.json"), "r", encoding="utf-8") as f:
        assert json.load(f)["status"] == "stopped"


def test_reconcile_manager_state_completed_when_rounds_done(tmp_path):
    root = str(tmp_path)
    d = os.path.join(root, "sim_y")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "run_state.json"), "w", encoding="utf-8") as f:
        json.dump({"runner_status": "running", "current_round": 72, "total_rounds": 72}, f)
    with open(os.path.join(d, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"simulation_id": "sim_y", "status": "running"}, f)

    reconcile_run_states(root)

    with open(os.path.join(d, "state.json"), "r", encoding="utf-8") as f:
        assert json.load(f)["status"] == "completed"


def test_manager_state_synced_even_when_run_state_already_terminal(tmp_path):
    # run_state finished cleanly but SimulationManager's state.json stayed
    # 'running' -> /api/simulation/list kept lying. Sync it regardless.
    root = str(tmp_path)
    d = os.path.join(root, "sim_z")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "run_state.json"), "w", encoding="utf-8") as f:
        json.dump({"runner_status": "completed", "current_round": 72, "total_rounds": 72}, f)
    with open(os.path.join(d, "state.json"), "w", encoding="utf-8") as f:
        json.dump({"simulation_id": "sim_z", "status": "running"}, f)

    reconcile_run_states(root)

    with open(os.path.join(d, "state.json"), "r", encoding="utf-8") as f:
        assert json.load(f)["status"] == "completed"


def _write_state(tmp_path, sim_id, state):
    import json, os
    d = tmp_path / sim_id
    d.mkdir(exist_ok=True)
    (d / "run_state.json").write_text(json.dumps(state), encoding="utf-8")
    return d


def test_watchdog_stops_a_wedged_completed_run(tmp_path):
    # Second occurrence in two days: all rounds complete on both platforms but
    # the runner never finalizes -- stays 'running' for hours, holds the queue
    # slot, blocks every queued job. The watchdog must stop it.
    from datetime import datetime, timedelta
    from app.utils.run_state_reconcile import find_wedged_runs
    now = datetime(2026, 7, 30, 12, 0, 0)
    stale = (now - timedelta(minutes=30)).isoformat()
    _write_state(tmp_path, "sim_wedged", {
        "runner_status": "running", "current_round": 72, "total_rounds": 72,
        "updated_at": stale,
    })
    _write_state(tmp_path, "sim_live", {
        "runner_status": "running", "current_round": 30, "total_rounds": 72,
        "updated_at": stale,
    })
    _write_state(tmp_path, "sim_fresh_done", {
        "runner_status": "running", "current_round": 72, "total_rounds": 72,
        "updated_at": (now - timedelta(minutes=2)).isoformat(),
    })
    _write_state(tmp_path, "sim_done", {
        "runner_status": "completed", "current_round": 72, "total_rounds": 72,
        "updated_at": stale,
    })
    assert find_wedged_runs(str(tmp_path), now=now) == ["sim_wedged"]


def test_watchdog_flags_stalled_mid_run_only_after_long_silence(tmp_path):
    # A mid-run heartbeat can pause legitimately for a while (slow LLM round);
    # only a very long silence counts as wedged
    from datetime import datetime, timedelta
    from app.utils.run_state_reconcile import find_wedged_runs
    now = datetime(2026, 7, 30, 12, 0, 0)
    _write_state(tmp_path, "sim_stalled", {
        "runner_status": "running", "current_round": 30, "total_rounds": 72,
        "updated_at": (now - timedelta(hours=3)).isoformat(),
    })
    assert find_wedged_runs(str(tmp_path), now=now) == ["sim_stalled"]


def test_watchdog_tick_is_throttled_and_calls_stopper(tmp_path):
    from datetime import datetime, timedelta
    from app.utils import run_state_reconcile as rsr
    now = datetime(2026, 7, 30, 12, 0, 0)
    stale = (now - timedelta(minutes=30)).isoformat()
    _write_state(tmp_path, "sim_wedged", {
        "runner_status": "running", "current_round": 72, "total_rounds": 72,
        "updated_at": stale,
    })
    stopped = []
    rsr._WATCHDOG_LAST = None    # reset module throttle for the test
    rsr.watchdog_tick(str(tmp_path), stopper=stopped.append, now=now)
    assert stopped == ["sim_wedged"]
    # immediate second tick: throttled, no re-stop even if state unchanged
    rsr.watchdog_tick(str(tmp_path), stopper=stopped.append, now=now)
    assert stopped == ["sim_wedged"]
