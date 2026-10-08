#!/usr/bin/env bash
# Nightly database backup on the production VM (plan 03-03, OPS-03). Runbook: docs/DEPLOY.md.
# Run by the pcbuilder-backup systemd timer (installed by scripts/server_setup.sh).
#
# 1. pg_dump (custom format) into /data/backups, keeping the newest 7 locally.
# 2. Refuse a dump under half the size of the previous one: something is wrong (a
#    truncated catalog, a failed dump) and it must not quietly replace a good backup.
# 3. Upload to the private OCI bucket pcbuilder-backups under daily/, deleting copies
#    older than 30 days. Auth is the VM's instance principal (dynamic group
#    pcbuilder-prod + policy pcbuilder-backups): no keys on the server.
# 4. Record the run in pipeline_runs as task "db_backup", so a failed or missing backup
#    turns /health/pipeline red and the uptime monitor emails the owner.
set -euo pipefail

APP=/srv/pcbuilder/app
BACKUPS=/data/backups
BUCKET="${OCI_BUCKET:-pcbuilder-backups}"
KEEP_LOCAL=7
KEEP_REMOTE_DAYS=30
OCI=/opt/oci-cli/bin/oci
# Asked from OCI, never typed in: a hand-copied namespace (digit 1 vs letter l) once made
# every upload fail with "BucketNotFound".
NAMESPACE="$("$OCI" os ns get --auth instance_principal --query data --raw-output)"

cd "$APP"
dc() { docker compose -f docker-compose.prod.yml --env-file ../.env "$@"; }
psql_q() { dc exec -T postgres psql -U pc_builder -d pc_builder -v ON_ERROR_STOP=1 -qAt -c "$1"; }

STARTED="$(date -u '+%Y-%m-%d %H:%M:%S')"
record() {  # status, counts-json, error
  local err="${3//\'/\'\'}"
  psql_q "INSERT INTO pipeline_runs (task, started_at, finished_at, status, counts, error)
          VALUES ('db_backup', '$STARTED', (now() AT TIME ZONE 'utc'), '$1', '$2'::jsonb,
                  NULLIF('$err', ''))" || echo "could not record the run in pipeline_runs" >&2
}
fail() { echo "BACKUP FAILED: $1" >&2; record failed '{}' "$1"; exit 1; }

NAME="pc_builder-$(date -u +%Y%m%dT%H%MZ).dump"
PREV="$(ls -1t "$BACKUPS"/pc_builder-*.dump 2>/dev/null | head -1 || true)"

dc exec -T postgres pg_dump -U pc_builder -d pc_builder -Fc > "$BACKUPS/$NAME.part" \
  || fail "pg_dump exited non-zero"
mv "$BACKUPS/$NAME.part" "$BACKUPS/$NAME"
SIZE=$(stat -c %s "$BACKUPS/$NAME")

if [[ -n "$PREV" ]]; then
  PREV_SIZE=$(stat -c %s "$PREV")
  if (( SIZE * 2 < PREV_SIZE )); then
    mv "$BACKUPS/$NAME" "$BACKUPS/$NAME.suspect"
    fail "dump is $SIZE bytes, under half of the previous ($PREV_SIZE); kept as $NAME.suspect, not uploaded"
  fi
fi

"$OCI" os object put --auth instance_principal --namespace "$NAMESPACE" --bucket-name "$BUCKET" \
  --name "daily/$NAME" --file "$BACKUPS/$NAME" --force >/dev/null \
  || fail "upload of $NAME to $BUCKET failed"

# Local retention: newest $KEEP_LOCAL dumps.
ls -1t "$BACKUPS"/pc_builder-*.dump | tail -n +$((KEEP_LOCAL + 1)) | xargs -r rm -f

# Remote retention: daily/ objects older than $KEEP_REMOTE_DAYS days.
CUTOFF="$(date -u -d "-$KEEP_REMOTE_DAYS days" +%Y%m%d)"
DELETED=0
for obj in $("$OCI" os object list --auth instance_principal --namespace "$NAMESPACE" \
               --bucket-name "$BUCKET" --prefix daily/ --all --query 'data[].name' --raw-output \
             | tr -d '[]", ' | grep . || true); do
  day="${obj#daily/pc_builder-}"; day="${day:0:8}"
  if [[ "$day" =~ ^[0-9]{8}$ && "$day" < "$CUTOFF" ]]; then
    "$OCI" os object delete --auth instance_principal --namespace "$NAMESPACE" \
      --bucket-name "$BUCKET" --name "$obj" --force >/dev/null && DELETED=$((DELETED + 1))
  fi
done

record ok "{\"file\": \"$NAME\", \"bytes\": $SIZE, \"remote_deleted\": $DELETED}" ""
echo "backup ok: $NAME ($SIZE bytes), uploaded to $BUCKET/daily/"
