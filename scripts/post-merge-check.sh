#!/bin/bash
# Guard-rail tripwire: run after every merge from upstream. Fails RED if a
# merge dropped any fork-owned cost/safety clamp (duration cap, activation
# cap, pipeline heal, watchdog, boot restore).
cd "$(dirname "$0")/.."
backend/.venv/Scripts/python.exe -m pytest \
  backend/tests/test_sim_duration_cap.py \
  backend/tests/test_pipeline_state.py \
  backend/tests/test_system_status.py \
  backend/tests/test_run_state_reconcile.py \
  backend/tests/test_boot_restore.py \
  -q || { echo; echo "!!! MERGE DROPPED A GUARD RAIL — fix before deploying !!!"; exit 1; }
echo "guard rails intact."
