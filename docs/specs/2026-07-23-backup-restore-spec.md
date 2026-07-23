# Backup & Restore — lite spec

## Purpose
Stop deploys and HF container restarts from wiping user data (the incident:
a redeploy erased a real run). Snapshot the entire data directory, restore it
after any wipe, and self-back-up nightly to a private HF Dataset.

## Data scope
Everything MiroFish persists lives under `backend/uploads/`:
`app_settings.json`, `projects/`, `reports/`, `simulations/`. Backup = a
`.tar.gz` of that directory; restore = extract it back.

## Components

### 1. Endpoints (gated by the access code — they sit under `/api/`)
- `GET /api/backup` → streams `mirofish-backup-<timestamp>.tar.gz` of the data dir.
- `POST /api/restore` (multipart file `archive`) → extracts into the data dir
  (path-traversal-safe), returns `{success, restored_entries}`.

### 2. Deploy safeguard (operator script, runs locally on every deploy)
`scripts/deploy_hf.sh`: **backup → push code → wait RUNNING → restore → verify**.
Pulls `/api/backup` off the live Space first (saved dated locally), pushes the
new snapshot, waits for the rebuild, POSTs the archive back to `/api/restore`,
and confirms entry counts match. A deploy without this sequence is the bug that
lost the run; the script makes the safe path the only path.

### 3. Nightly self-backup (in-container, covers HF's own restarts)
A daemon thread started in `create_app` **only when** `BACKUP_HF_REPO` and
`HF_TOKEN` are set (off in local dev): once per day it tars the data dir and
uploads it to the private HF Dataset via `huggingface_hub`, keeping a dated
history. Restore-on-boot is manual via the endpoint (a fresh container starts
empty; operator or a future auto-restore pulls the latest).

## Behaviors (entry → action → result)
1. **Backup.** GET `/api/backup` with a valid session → 200, a `.tar.gz`
   attachment containing the full data tree. Unauthenticated → 401 (gate).
2. **Restore.** POST `/api/restore` with an archive → files written under the
   data dir; existing files overwritten by archived ones; response reports the
   count. Malicious paths (`../`, absolute) are rejected, never written.
3. **Round-trip.** backup → wipe the data dir → restore → the data dir is
   byte-identical to before.
4. **Nightly.** With `BACKUP_HF_REPO`+`HF_TOKEN` set, once a day the container
   pushes a dated archive to the Dataset. Unset → thread never starts.

## Implementation shape
- `backend/app/utils/backup.py` — pure helpers: `make_backup_bytes(data_dir)`,
  `restore_from_bytes(archive, data_dir)` (rejects unsafe members),
  `should_backup(last_iso, now, min_interval_hours=24)`. Unit-tested.
- `backend/app/api/backup.py` — the two routes, registered in `create_app`.
- `backend/app/services/backup_scheduler.py` — the daily daemon thread +
  `push_to_hf(bytes, repo, token)` (huggingface_hub); started from `create_app`
  when env is present.
- `huggingface_hub` added to backend deps.
- `scripts/deploy_hf.sh` — the operator safeguard.

## Testing
- pytest: archive round-trip (make→restore == identity); path-traversal member
  rejected; `should_backup` cadence (fires at ≥24h, skips under); endpoints
  (GET returns gzip attachment, POST restores + counts, both 401 when gated).
- End-to-end local: backup → delete uploads/ contents → restore → verify tree
  restored.

## Out of scope
- Auto-restore-on-boot (manual/scripted for now; add later if needed).
- Encryption at rest in the Dataset (it's private; add GPG later if required).
- Per-user or partial backups (whole-dir only).
