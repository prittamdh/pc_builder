#!/usr/bin/env bash
# Copy the newest production database dump to this (home) PC: the backup that lives
# off Oracle, for the day the Oracle account or VM is lost (plan 03-03, OPS-03/09).
#
#   scripts/pull_backup.sh
#
# Keeps the newest 8 copies in $BACKUP_DIR (default ~/pcbuilder-backups): about two
# months of weekly pulls. Run it weekly (Windows Task Scheduler, see docs/DEPLOY.md).
# Fails loudly if the newest dump on the VM is more than 2 days old.
set -euo pipefail

HOST="${DEPLOY_HOST:-ubuntu@144.24.104.36}"
KEY="${DEPLOY_KEY:-$HOME/.ssh/pcbuilder_oracle}"
DIR="${BACKUP_DIR:-$HOME/pcbuilder-backups}"
KEEP=8

mkdir -p "$DIR"
NEWEST="$(ssh -i "$KEY" -o ConnectTimeout=20 "$HOST" \
  'find /data/backups -name "pc_builder-*.dump" -mtime -2 -printf "%T@ %p\n" | sort -n | tail -1 | cut -d" " -f2')"
if [[ -z "$NEWEST" ]]; then
  echo "PULL FAILED: no dump from the last 2 days on the VM - check the nightly backup" >&2
  exit 1
fi

scp -q -i "$KEY" "$HOST:$NEWEST" "$DIR/"
NAME="$(basename "$NEWEST")"
SIZE=$(stat -c %s "$DIR/$NAME" 2>/dev/null || wc -c < "$DIR/$NAME")
ls -1t "$DIR"/pc_builder-*.dump | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "pulled $NAME ($SIZE bytes) to $DIR"
