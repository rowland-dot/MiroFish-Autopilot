#!/usr/bin/env bash
# Safe deploy to the Hugging Face Space: BACKUP → PUSH → WAIT → RESTORE → VERIFY.
# A plain `git push` to the Space wipes its ephemeral disk; this script pulls
# the live data first and restores it after the rebuild, so no run is lost.
#
# Requires (env):
#   HF_TOKEN     write token for the Space
#   HF_SPACE     e.g. leeroyy1288/mirofish
#   ACCESS_CODE  the deployment's access code (backup/restore are gated)
# Run from the repo root, on the branch you want to deploy (usually main).
set -euo pipefail

# Auto-load saved deploy credentials (gitignored, never pushed). Lets a plain
# `bash scripts/deploy_hf.sh` run with zero prompts. Shell env still wins.
DEPLOY_ENV="$(dirname "$0")/.deploy.env"
if [ -f "$DEPLOY_ENV" ]; then set -a; . "$DEPLOY_ENV"; set +a; fi

: "${HF_TOKEN:?set HF_TOKEN}" "${HF_SPACE:?set HF_SPACE}" "${ACCESS_CODE:?set ACCESS_CODE}"
HOST=$(printf '%s' "$HF_SPACE" | tr '/' '-')
BASE="https://${HOST}.hf.space"
STAMP=$(date +%Y%m%d-%H%M%S)
BK="mirofish-backup-${STAMP}.tar.gz"
JAR=$(mktemp)

login() { curl -s -c "$JAR" -o /dev/null -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' -d "{\"code\":\"$ACCESS_CODE\"}"; }

echo "0/5  Checking for a running job (never disrupt one) ..."
login
BUSY=$(curl -s -b "$JAR" "$BASE/api/status" \
  | python -c "import sys,json;print(json.load(sys.stdin).get('data',{}).get('busy'))" 2>/dev/null || echo "unknown")
if [ "$BUSY" = "True" ] || [ "$BUSY" = "true" ]; then
  echo "     ABORTED: a simulation or report job is currently running on the Space."
  echo "     Deploying now would kill it. Re-run this deploy once the job finishes."
  curl -s -b "$JAR" "$BASE/api/status"; echo
  exit 3
fi
if [ "$BUSY" = "unknown" ]; then
  echo "     WARNING: could not read /api/status (older version without it?)."
  echo "     Confirm nothing is running before continuing, or Ctrl-C now."
  sleep 5
fi
echo "     idle — safe to proceed."

echo "1/5  Backing up live data from $BASE ..."
# HARD RULE: a code push wipes the ephemeral disk. If we cannot obtain a
# VALID backup first, we ABORT — never proceed without one (that once
# destroyed a completed run). Override only with ALLOW_NO_BACKUP=1 after a
# deliberate decision that nothing on the Space needs keeping.
login
curl -s -b "$JAR" "$BASE/api/backup" -o "$BK" 2>/dev/null || true
# A valid backup is a real gzip tar with >0 data entries. Empty/broken
# backups (e.g. a 173-byte stub or an HTML error page) do NOT count.
BEFORE=$(tar -tzf "$BK" 2>/dev/null | grep -cE 'simulations/|projects/|reports/' || echo 0)
BK_SIZE=$(wc -c < "$BK" 2>/dev/null || echo 0)
if [ "$BEFORE" -lt 1 ] || [ "$BK_SIZE" -lt 1024 ]; then
  if [ "${ALLOW_NO_BACKUP:-0}" = "1" ]; then
    echo "     WARNING: no valid backup (entries=$BEFORE size=$BK_SIZE) but ALLOW_NO_BACKUP=1 — proceeding."
    BK=""; BEFORE=0
  else
    echo "     ABORTED: could not obtain a valid pre-deploy backup (entries=$BEFORE, size=$BK_SIZE bytes)."
    echo "     A push would wipe the disk with no way back. Fix /api/backup, or"
    echo "     re-run with ALLOW_NO_BACKUP=1 ONLY if the Space has nothing worth keeping."
    rm -f "$BK" "$JAR"
    exit 4
  fi
else
  echo "     saved $BK  ($BEFORE data entries, $BK_SIZE bytes)"
fi

echo "2/5  Pushing code snapshot ..."
SNAPDIR=$(mktemp -d)
git worktree add --detach "$SNAPDIR" main >/dev/null 2>&1
( cd "$SNAPDIR"
  git rm -rq static/image >/dev/null 2>&1 || true
  git lfs track "*.jpeg" "*.jpg" "*.png" "*.gif" >/dev/null 2>&1 || true
  git add .gitattributes >/dev/null 2>&1 || true
  git rm -q --cached frontend/src/assets/logo/*.jpeg >/dev/null 2>&1 || true
  git add frontend/src/assets/logo/ >/dev/null 2>&1 || true
  TREE=$(git write-tree)
  SNAP=$(git commit-tree "$TREE" -m "MiroFish deploy $STAMP")
  git push "https://${HF_SPACE%%/*}:${HF_TOKEN}@huggingface.co/spaces/${HF_SPACE}" \
    "$SNAP:refs/heads/main" --force )
git worktree remove --force "$SNAPDIR" >/dev/null 2>&1 || true

echo "3/5  Waiting for RUNNING ..."
for _ in $(seq 1 60); do
  ST=$(curl -s "https://huggingface.co/api/spaces/${HF_SPACE}" \
       | python -c "import sys,json;print(json.load(sys.stdin).get('runtime',{}).get('stage','?'))" 2>/dev/null || echo '?')
  [ "$ST" = "RUNNING" ] && break
  case "$ST" in BUILD_ERROR|RUNTIME_ERROR) echo "     build failed: $ST"; exit 1;; esac
  sleep 15
done
echo "     stage=$ST"

if [ -n "$BK" ]; then
  echo "4/5  Restoring data ..."
  login
  RESP=$(curl -s -b "$JAR" -X POST "$BASE/api/restore" -F "archive=@$BK")
  echo "     $RESP"
  echo "5/5  Verify: backed up $BEFORE entries; restore response above."
else
  echo "4/5  No backup to restore (first deploy)."
  echo "5/5  Done — future deploys will be backed up automatically."
fi
rm -f "$JAR"
echo "Deploy complete: $BASE"
