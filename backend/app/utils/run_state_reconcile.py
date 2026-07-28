"""Finalize stale run_state records left behind by a restart.

A container restart (deploy, crash, OOM) kills the OASIS subprocess but never
updates run_state.json, so the record stays 'running' forever. The UI then
shows a phantom running job and the frontend driver polls a run that will
never reach a terminal state.

Called once at app start. Isolated module — does NOT touch simulation_runner.py
(upstream-owned hot file); it only rewrites the JSON records on disk.
"""

import json
import os

from .logger import logger

_NON_TERMINAL = ("running", "starting", "stopping", "paused")


def finalize_status(state: dict):
    """Terminal status for a stale record, or None if it needs no change.

    Rounds complete -> completed; otherwise the run was cut short -> stopped.
    """
    if (state or {}).get("runner_status") not in _NON_TERMINAL:
        return None
    current = state.get("current_round") or 0
    total = state.get("total_rounds") or 0
    return "completed" if total > 0 and current >= total else "stopped"


def reconcile_run_states(run_state_dir: str) -> list:
    """Rewrite every stale record under run_state_dir. Returns ids changed.

    Safe on a missing directory and on corrupt files (skipped, never raises) —
    reconciliation must never block app start.
    """
    changed = []
    if not os.path.isdir(run_state_dir):
        return changed
    for sim_id in os.listdir(run_state_dir):
        path = os.path.join(run_state_dir, sim_id, "run_state.json")
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue                      # corrupt/unreadable -> leave alone
        new_status = finalize_status(state)
        if not new_status:
            continue
        state["runner_status"] = new_status
        state["twitter_running"] = False
        state["reddit_running"] = False
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            changed.append(sim_id)
        except OSError:
            continue
    return changed


def reconcile_on_start(run_state_dir: str) -> None:
    """App-start hook: finalize corpses, log what was cleaned."""
    try:
        changed = reconcile_run_states(run_state_dir)
        if changed:
            logger.info(f"启动清理：已终结 {len(changed)} 条重启遗留的运行记录: {changed}")
    except Exception as e:      # never block startup
        logger.error(f"运行记录清理失败: {e}")
