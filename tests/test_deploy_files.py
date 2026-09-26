"""Static checks on the production deploy files (plan 03-02, OPS-01/02/08, SEC-08).

These don't need Docker: they read the files and pin the properties that matter for
safety, so an edit can't quietly publish Postgres, run as root, or drop the migration.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def compose():
    return yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))


def test_only_caddy_publishes_ports():
    services = compose()["services"]
    published = {name for name, svc in services.items() if svc.get("ports")}
    assert published == {"caddy"}
    assert sorted(services["caddy"]["ports"]) == ["443:443", "80:80"]


def test_postgres_data_and_caddy_state_live_on_the_data_volume():
    services = compose()["services"]
    assert "/data/postgres:/var/lib/postgresql/data" in services["postgres"]["volumes"]
    assert "/data/caddy:/data" in services["caddy"]["volumes"]


def test_api_and_worker_run_in_production_mode_from_one_image():
    services = compose()["services"]
    for name in ("api", "worker"):
        assert services[name]["environment"]["ENV"] == "production"
        assert services[name]["image"] == "pcbuilder-app:latest"
        assert services[name]["env_file"] == "../.env"
    assert services["worker"]["command"] == ["python", "-m", "pipeline.worker"]


def test_postgres_major_version_matches_the_local_database():
    # A pg_dump from the home machine (postgres:15 in docker-compose.yml) must restore as is.
    local = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    assert local["services"]["postgres"]["image"].split(":")[1].split("-")[0] == "15"
    assert compose()["services"]["postgres"]["image"].startswith("postgres:15")


def test_image_never_runs_as_root_and_runs_one_api_process():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "\nUSER app\n" in dockerfile
    assert "--workers" not in dockerfile


def test_secrets_never_go_into_the_image():
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert ".env" in ignore and ".env.*" in ignore
    assert ".git" in ignore


def test_caddy_caps_request_bodies():
    caddyfile = (ROOT / "Caddyfile").read_text(encoding="utf-8")
    assert "max_size 10MB" in caddyfile
    assert "reverse_proxy api:8000" in caddyfile


def test_deploy_runs_the_full_suite_with_e2e_required_then_migrates():
    deploy = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert "REQUIRE_E2E=1 python -m pytest" in deploy
    assert "up -d --wait postgres" in deploy
    migrate = deploy.index("run --rm --no-deps api alembic upgrade head")
    assert deploy.index("up -d --wait postgres") < migrate < deploy.index("up -d --remove-orphans")
    assert "git archive" in deploy
    assert "chmod 600 /srv/pcbuilder/.env" in deploy


def test_backup_script_is_loud_and_keyless():
    backup = (ROOT / "scripts" / "backup_db.sh").read_text(encoding="utf-8")
    assert "set -euo pipefail" in backup
    assert "pg_dump -U pc_builder -d pc_builder -Fc" in backup
    assert "--auth instance_principal" in backup           # no API key on the server
    assert "SIZE * 2 < PREV_SIZE" in backup                # refuses a suspiciously small dump
    assert "'db_backup'" in backup                         # recorded for /health/pipeline
    assert "record failed" in backup


def test_server_setup_installs_the_nightly_backup_timer():
    setup = (ROOT / "scripts" / "server_setup.sh").read_text(encoding="utf-8")
    assert "OnCalendar=*-*-* 21:30:00 UTC" in setup
    assert "Persistent=true" in setup
    assert "systemctl enable --now pcbuilder-backup.timer" in setup
    assert "PasswordAuthentication no" in setup


def test_shell_scripts_have_unix_line_endings():
    """They run on Linux; a CRLF checkout once broke server_setup.sh ('pipefail:
    invalid option name'). .gitattributes pins *.sh to LF."""
    for path in (ROOT / "scripts").glob("*.sh"):
        assert b"\r\n" not in path.read_bytes(), path.name
    assert "*.sh text eol=lf" in (ROOT / ".gitattributes").read_text(encoding="utf-8")


def test_only_cloudflare_reaches_the_web_ports_on_the_vm():
    fw = (ROOT / "scripts" / "firewall_cloudflare.sh").read_text(encoding="utf-8")
    assert "https://www.cloudflare.com/ips-v4" in fw
    assert "DOCKER-USER" in fw          # Docker-published ports skip INPUT
    assert "iptables -A PCB-CF -j DROP" in fw
    setup = (ROOT / "scripts" / "server_setup.sh").read_text(encoding="utf-8")
    assert "PartOf=docker.service" in setup     # re-applied when Docker restarts


def test_caddy_redirects_www_and_sends_hsts():
    caddyfile = (ROOT / "Caddyfile").read_text(encoding="utf-8")
    assert 'Strict-Transport-Security "max-age=31536000"' in caddyfile
    assert "redir @www https://{re.www.1}{uri} permanent" in caddyfile
