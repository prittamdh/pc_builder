"""The extension's static checks and its Node unit tests (plan 02-05, AGENT-10)."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scrapers.store_hosts import STORE_DOMAINS

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"


def _manifest():
    return json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_is_mv3_with_only_the_permissions_it_needs():
    m = _manifest()
    assert m["manifest_version"] == 3
    assert sorted(m["permissions"]) == ["alarms", "storage"]
    assert m["background"] == {"service_worker": "background.js", "type": "module"}


def test_store_hosts_match_in_python_manifest_and_extension_code():
    """One list in three places: the server's refusal list, the extension's host
    permissions, and the extension's own fetch check."""
    m = _manifest()
    stores_in_manifest = {
        re.sub(r"^https://(\*\.)?", "", pat).removesuffix("/*")
        for pat in m["host_permissions"] if pat.startswith("https://")
    }
    assert stores_in_manifest == set(STORE_DOMAINS)
    for d in STORE_DOMAINS:
        assert f"https://{d}/*" in m["host_permissions"]
        assert f"https://*.{d}/*" in m["host_permissions"]

    core = (EXT / "agent_core.js").read_text(encoding="utf-8")
    block = re.search(r"STORE_DOMAINS = \[(.*?)\];", core, re.S).group(1)
    assert re.findall(r'"([^"]+)"', block) == list(STORE_DOMAINS)


def test_the_only_non_store_hosts_are_local_and_asked_for_at_runtime():
    m = _manifest()
    others = [p for p in m["host_permissions"] if not p.startswith("https://")]
    assert others == ["http://localhost/*", "http://127.0.0.1/*"]
    assert m["optional_host_permissions"] == ["http://*/*", "https://*/*"]


def test_store_fetches_never_send_cookies():
    core = (EXT / "agent_core.js").read_text(encoding="utf-8")
    assert 'credentials: "omit"' in core
    assert 'cache: "no-store"' in core


def test_node_unit_tests_pass():
    node = shutil.which("node")
    if node is None:
        if os.environ.get("REQUIRE_E2E") == "1":
            pytest.fail("node not installed")
        pytest.skip("node not installed")
    result = subprocess.run(
        [node, "--test", str(EXT / "tests" / "agent_core.test.mjs")],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
