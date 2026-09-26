#!/usr/bin/env bash
# Deploy the committed code to the production VM (plan 03-02, OPS-01). Runbook: docs/DEPLOY.md.
#
#   scripts/deploy.sh            # deploy HEAD
#   scripts/deploy.sh main       # deploy a branch, tag or commit
#
# Steps: run the whole test suite with REQUIRE_E2E=1 (a skipped browser test is a failure,
# not a pass); ship the committed tree (git archive, so uncommitted edits never reach
# production and the VM needs no GitHub access); build the image on the VM; run
# `alembic upgrade head`; restart; smoke-test /health through Caddy. The previous code
# stays in /srv/pcbuilder/app.prev for a rollback.
#
# Env: DEPLOY_HOST (default ubuntu@144.24.104.36), DEPLOY_KEY (default
# ~/.ssh/pcbuilder_oracle), SKIP_TESTS=1 only to redeploy a commit that already passed.
set -euo pipefail

REF="${1:-HEAD}"
HOST="${DEPLOY_HOST:-ubuntu@144.24.104.36}"
KEY="${DEPLOY_KEY:-$HOME/.ssh/pcbuilder_oracle}"
SSH=(ssh -i "$KEY" -o ConnectTimeout=20 "$HOST")

cd "$(git rev-parse --show-toplevel)"
COMMIT="$(git rev-parse --short "$REF")"
echo "==> deploying $REF ($COMMIT) to $HOST"

if [[ "${SKIP_TESTS:-0}" != "1" ]]; then
  echo "==> test suite (REQUIRE_E2E=1)"
  REQUIRE_E2E=1 python -m pytest -q -p no:randomly
fi

echo "==> shipping code"
git archive --format=tar "$REF" | "${SSH[@]}" "set -e
  rm -rf /srv/pcbuilder/app.new && mkdir -p /srv/pcbuilder/app.new
  tar -x -C /srv/pcbuilder/app.new
  echo $COMMIT > /srv/pcbuilder/app.new/DEPLOYED_COMMIT"

echo "==> build, migrate, restart"
"${SSH[@]}" "set -e
  test -f /srv/pcbuilder/.env || { echo 'missing /srv/pcbuilder/.env - see docs/DEPLOY.md' >&2; exit 1; }
  chmod 600 /srv/pcbuilder/.env
  cd /srv/pcbuilder
  rm -rf app.prev
  if [ -d app ]; then mv app app.prev; fi
  mv app.new app
  cd app
  dc='docker compose -f docker-compose.prod.yml --env-file ../.env'
  \$dc build --pull api
  \$dc up -d --wait postgres   # migrations must not race Postgres starting up
  \$dc run --rm --no-deps api alembic upgrade head
  \$dc up -d --remove-orphans
  \$dc ps"

echo "==> smoke test"
for i in $(seq 1 30); do
  if "${SSH[@]}" "curl -fsS -o /dev/null -w '%{http_code}' http://localhost/health" 2>/dev/null | grep -q 200; then
    echo "==> /health is 200 through Caddy: $COMMIT is live"
    exit 0
  fi
  sleep 3
done
echo "!! /health did not come up. Logs: ssh $HOST 'cd /srv/pcbuilder/app && docker compose -f docker-compose.prod.yml logs --tail 100 api'" >&2
echo "!! Roll back: see docs/DEPLOY.md, \"Rollback\"." >&2
exit 1
