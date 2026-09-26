# Deploying PC Builder

Production is one Oracle Cloud VM. This page is the whole setup: with the git repo, an
off-Oracle database dump and this page, the site can be rebuilt on a fresh VM.

## What runs where

| Piece | Where |
|---|---|
| VM | Oracle Cloud, Mumbai (`ap-mumbai-1`), `pcbuilder-prod`, VM.Standard.A1.Flex 2 OCPU / 12 GB (Always Free), Ubuntu 24.04 arm64 |
| Public IP | `144.24.104.36` (ephemeral: it changes only if the VM is deleted) |
| Network | VCN `pcbuilder-vcn`, public subnet `pcbuilder-public`, internet gateway `pcbuilder-igw`, default route table `0.0.0.0/0 -> pcbuilder-igw` |
| Disks | 47 GB boot (OS, Docker images); 150 GB block volume `pcbuilder-data` mounted at `/data` (Postgres, Caddy state, backups, container logs) |
| Code | `/srv/pcbuilder/app` (unpacked by `scripts/deploy.sh`; previous release in `app.prev`) |
| Secrets | `/srv/pcbuilder/.env`, mode 600, never in git |
| Containers | `docker-compose.prod.yml`: `caddy` (ports 80/443), `api`, `worker`, `postgres` (no host port) |
| Cost guard | OCI budget `zero-spend-guard`: alert at 100% of 1/month, emailed to the owner |

Everything counts against the Always Free allowance: 2 OCPU / 12 GB of A1, 200 GB of
block storage (47 + 150 used). The account is pay-as-you-go (upgraded 2026-09-26: the
Free Trial could not get A1 capacity in Mumbai), so a paid resource *can* be created by
mistake. When creating anything, pick shapes and sizes marked "Always Free-eligible":
the create-instance form now defaults to the paid E5.Flex shape, and the block-volume
form to 1024 GB.

## Log in

```
ssh -i ~/.ssh/pcbuilder_oracle ubuntu@144.24.104.36
```

Password login is off. The private key is only on the owner's PC; lose it and you need
the Oracle console's "Console connection" to add a new one.

Useful once logged in (`dc` = `docker compose -f docker-compose.prod.yml --env-file ../.env`,
run from `/srv/pcbuilder/app`):

```
dc ps                          # what is running
dc logs --tail 100 -f api      # API log (also: worker, caddy, postgres)
dc exec postgres psql -U pc_builder pc_builder
cat /srv/pcbuilder/app/DEPLOYED_COMMIT
```

Postgres has no public port. From the owner's PC, reach it through SSH:
`ssh -i ~/.ssh/pcbuilder_oracle -L 5433:localhost:5432 ubuntu@144.24.104.36`, then run
`dc exec` there, or add a port mapping only on `127.0.0.1` temporarily.

## Deploy

From the repo on the owner's PC, with the change committed:

```
scripts/deploy.sh
```

It runs the whole test suite with `REQUIRE_E2E=1` (about 12 minutes; a skipped browser
test fails the deploy), ships the committed tree with `git archive` (uncommitted edits
never reach production; the VM needs no GitHub access), builds the image on the VM,
starts Postgres and waits until it is healthy, runs `alembic upgrade head`, restarts
everything, and checks `/health` through Caddy. `SKIP_TESTS=1 scripts/deploy.sh` only
for redeploying a commit that already passed.

### Rollback

```
ssh -i ~/.ssh/pcbuilder_oracle ubuntu@144.24.104.36
cd /srv/pcbuilder && mv app app.bad && mv app.prev app && cd app
docker compose -f docker-compose.prod.yml --env-file ../.env up -d --build
```

A migration is not undone by this. If the bad release migrated the database, either
downgrade (`dc run --rm api alembic downgrade -1`, when that migration has a working
downgrade) or restore the last dump.

## Secrets: /srv/pcbuilder/.env

Created on the VM, never copied through chat or git. Keys (see `.env.example` for all):

- `POSTGRES_PASSWORD`: generated on the VM at setup (`openssl rand -hex 24`).
- `ENV=production`: hides `/docs`, sets production behaviour.
- `SCRAPE_VIA_AGENTS=true`: production never fetches store pages itself; the worker
  queues jobs for the browser extensions (and `HttpClient` refuses store hosts anyway).
- LLM keys (`MISTRAL_API_KEY`, `GOOGLE_API_KEY`, ...): the owner pastes them in by hand
  (`nano /srv/pcbuilder/.env`), then `dc up -d` to apply. Without them the worker's
  extraction steps fail and `/health/pipeline` says so.
- Later: `SITE_ADDRESS` (the domain), `CONTACT_EMAIL`, `TRUST_CF_CONNECTING_IP=true`
  once only Cloudflare can reach the VM.

## Health checks (for the uptime monitor)

| URL | 503 when |
|---|---|
| `/health` | the database does not answer |
| `/health/freshness` | no price saved in 24 h |
| `/health/pipeline` | no agent checked in for 24 h, no price for 24 h, or a worker task failed or is late |

Until the domain exists, test from the VM: `curl -s localhost/health`.

## Rebuild from scratch (the drill, OPS-09)

1. **VM**: Oracle console, Compute, Create instance. Shape VM.Standard.A1.Flex, 2 OCPU,
   12 GB (check "Always Free-eligible"); image Canonical Ubuntu 24.04; network
   `pcbuilder-vcn` / public subnet (if the VCN is new, it needs an internet gateway and a
   `0.0.0.0/0` route to it, or SSH times out); paste `~/.ssh/pcbuilder_oracle.pub`.
   After creation: the VNIC's IP administration, Edit, Ephemeral public IP.
2. **Data disk**: Storage, Block volumes, Create: custom size 150 GB (not the 1024 GB
   default), Balanced, no backup policy, same AD. Attached instances, Attach:
   Paravirtualized, read/write. On the VM:
   ```
   sudo mkfs.ext4 -L pcbuilder-data /dev/sdb          # only on a NEW, empty disk
   sudo mkdir -p /data
   echo "UUID=$(sudo blkid -o value -s UUID /dev/sdb) /data ext4 defaults,noatime,nofail,_netdev 0 2" | sudo tee -a /etc/fstab
   sudo mount /data
   ```
3. **Base setup**: `scp scripts/server_setup.sh ubuntu@<ip>:/tmp/ && ssh ubuntu@<ip> 'sudo bash /tmp/server_setup.sh'`
   (Docker, logs rotated at 10 MB x 5, password SSH off, security updates on).
4. **Secrets**: create `/srv/pcbuilder/.env` as above (`umask 077` first).
5. **Database**: restore the newest dump into the `postgres` container before or after
   the first deploy (`pg_restore` into `pc_builder`); then deploy runs
   `alembic upgrade head`, a no-op if the dump is current. An empty database also works:
   the migrations build the full schema.
6. **Deploy**: `DEPLOY_HOST=ubuntu@<new-ip> scripts/deploy.sh`.
7. Point Cloudflare DNS at the new IP.

Record how long each step took in the drill notes.

## Not done yet (Phase 3)

- Domain, Cloudflare proxy, Origin CA certificate, HSTS (then `SITE_ADDRESS` in `.env`).
- OCI security list and host firewall: open 80/443 to Cloudflare's ranges only (OPS-02).
  Today the host firewall (Oracle's iptables rules) allows only SSH.
- Nightly `pg_dump` to OCI Object Storage and weekly to R2 (03-03).
- Sentry (needs the `sentry-sdk` package approved).
