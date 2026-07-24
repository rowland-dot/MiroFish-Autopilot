#!/usr/bin/env bash
# Wait for the Space to be idle, then run the safe deploy. Retries only on
# exit code 3 (a job is running); any other failure stops immediately.
# Polls every 2 min for up to ~3 hours. Local-only helper (not pushed).
set -uo pipefail
cd "$(dirname "$0")/.."

MAX_MIN=180
INTERVAL=120
elapsed=0
while :; do
  bash scripts/deploy_hf.sh
  rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "WATCHER: deploy succeeded after ${elapsed}s of waiting."
    exit 0
  fi
  if [ "$rc" -ne 3 ]; then
    echo "WATCHER: deploy failed with exit $rc (not a busy-abort) — stopping."
    exit "$rc"
  fi
  if [ "$elapsed" -ge $((MAX_MIN * 60)) ]; then
    echo "WATCHER: still busy after ${MAX_MIN} min — giving up; re-run when free."
    exit 3
  fi
  echo "WATCHER: job still running; re-checking in ${INTERVAL}s (waited ${elapsed}s)."
  sleep "$INTERVAL"
  elapsed=$((elapsed + INTERVAL))
done
