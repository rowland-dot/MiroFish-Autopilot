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
from datetime import datetime

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
            # run_state is already terminal, but SimulationManager's state.json
            # can still be stuck on 'running' (that is what made
            # /api/simulation/list report a run that had finished). Sync it.
            rs = (state or {}).get("runner_status")
            if rs in ("completed", "stopped", "failed"):
                _finalize_manager_state(os.path.join(run_state_dir, sim_id), rs)
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
        # SimulationManager keeps its OWN state.json; a restart leaves that
        # stuck on 'running' too (that is why /api/simulation/list kept
        # reporting a run that no longer exists). Finalize it to match.
        _finalize_manager_state(os.path.join(run_state_dir, sim_id), new_status)
    return changed


def _finalize_manager_state(sim_dir: str, new_status: str) -> None:
    path = os.path.join(sim_dir, "state.json")
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    if data.get("status") not in _NON_TERMINAL:
        return
    data["status"] = new_status
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def reconcile_on_start(run_state_dir: str) -> None:
    """App-start hook: finalize corpses, log what was cleaned."""
    try:
        changed = reconcile_run_states(run_state_dir)
        if changed:
            logger.info(f"启动清理：已终结 {len(changed)} 条重启遗留的运行记录: {changed}")
    except Exception as e:      # never block startup
        logger.error(f"运行记录清理失败: {e}")


# ---- live-wedge watchdog -------------------------------------------------
# 与上面的「重启后清尸」不同：这里对付的是进程还活着、但收尾卡死的 run——
# 两个平台的轮次都跑满了，runner 却停在 'running' 不出来，一挂就是几小时，
# 占着并发槽位把整个队列冻住（两天内发生了两次）。
#
# 判定（宁可保守）：
#   - 轮次已跑满 + 心跳（updated_at）停更超过 10 分钟   -> 收尾卡死
#   - 轮次未跑满 + 心跳停更超过 2 小时                  -> 中途卡死
# 心跳每 ~2s 覆写一次，10 分钟静默对「已完成」的 run 来说绰绰有余；
# 中途的 run 单轮 LLM 可能很慢，阈值放到 2 小时避免误杀。

# 45 分钟：驱动器现在自己负责「轮次跑满 -> 就地报告 -> 主动 stop」。
# 看门狗只兜底（浏览器死掉没人报告/停止的场景），过早停会杀掉报告期的
# 活体 interview 能力。
_WEDGE_DONE_SECONDS = 45 * 60
_WEDGE_MIDRUN_SECONDS = 2 * 3600
_WATCHDOG_INTERVAL_SECONDS = 60
_WATCHDOG_LAST = None


def find_wedged_runs(run_state_dir: str, now: datetime = None) -> list:
    """Ids of live-but-wedged runs. Pure read; never raises."""
    now = now or datetime.now()
    out = []
    if not os.path.isdir(run_state_dir):
        return out
    for sim_id in sorted(os.listdir(run_state_dir)):
        path = os.path.join(run_state_dir, sim_id, "run_state.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if st.get("runner_status") != "running":
            continue
        heartbeat = st.get("updated_at") or st.get("started_at")
        try:
            age = (now - datetime.fromisoformat(heartbeat)).total_seconds()
        except (TypeError, ValueError):
            continue                     # 无法判定心跳：不动它
        total = st.get("total_rounds") or 0
        done = total > 0 and (st.get("current_round") or 0) >= total
        limit = _WEDGE_DONE_SECONDS if done else _WEDGE_MIDRUN_SECONDS
        if age > limit:
            out.append(sim_id)
    return out


def _default_stopper(sim_id: str) -> None:
    from ..services.simulation_runner import SimulationRunner
    SimulationRunner.stop_simulation(sim_id)


def watchdog_tick(run_state_dir: str, stopper=None, now: datetime = None) -> list:
    """Stop every wedged run. Throttled (>=60s between scans); never raises.

    Called from hot read paths (/api/status, /api/pipeline) so no scheduler
    is needed — any open browser or the deploy script keeps it beating.
    """
    global _WATCHDOG_LAST
    now = now or datetime.now()
    if _WATCHDOG_LAST is not None and (now - _WATCHDOG_LAST).total_seconds() < _WATCHDOG_INTERVAL_SECONDS:
        return []
    _WATCHDOG_LAST = now
    stopper = stopper or _default_stopper
    stopped = []
    for sim_id in find_wedged_runs(run_state_dir, now=now):
        try:
            stopper(sim_id)
            stopped.append(sim_id)
            logger.warning(f"看门狗：run {sim_id} 收尾卡死（轮次已完成但状态停在 running），已强制停止")
        except Exception as e:          # noqa: BLE001 — 看门狗绝不能拖垮读接口
            logger.error(f"看门狗停止 {sim_id} 失败: {e}")
    return stopped
