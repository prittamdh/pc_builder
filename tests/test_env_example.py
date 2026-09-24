"""SEC-08: .env.example must document every variable the code and compose files read."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
ENV_EXAMPLE = ROOT / ".env.example"

FORBIDDEN_SUBSTRINGS = ["pc_builder123", "sk-", "gsk_", "AIza"]

_GETENV_RE = re.compile(r'os\.(?:getenv|environ\.get)\(\s*["\'](\w+)["\']')
_ENVIRON_ITEM_RE = re.compile(r'os\.environ\[\s*["\'](\w+)["\']\s*\]')
_COMPOSE_VAR_RE = re.compile(r'\$\{(\w+)(?::[^}]*)?\}')


def _code_keys() -> set[str]:
    keys = set()
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        keys.update(_GETENV_RE.findall(text))
        keys.update(_ENVIRON_ITEM_RE.findall(text))
    return keys


def _compose_keys() -> set[str]:
    keys = set()
    for path in ROOT.glob("docker-compose*.yml"):
        text = path.read_text(encoding="utf-8", errors="replace")
        keys.update(_COMPOSE_VAR_RE.findall(text))
    return keys


def _parse_env_example() -> list[tuple[str, str]]:
    pairs = []
    text = ENV_EXAMPLE.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        pairs.append((key.strip(), value.strip()))
    return pairs


def test_env_example_exists():
    assert ENV_EXAMPLE.exists()


def test_every_code_key_is_documented():
    pairs = _parse_env_example()
    example_keys = {k for k, _ in pairs}
    missing = _code_keys() - example_keys
    assert not missing, f"Missing from .env.example: {sorted(missing)}"


def test_every_compose_key_is_documented():
    pairs = _parse_env_example()
    example_keys = {k for k, _ in pairs}
    missing = _compose_keys() - example_keys
    assert not missing, f"Missing from .env.example: {sorted(missing)}"


def test_no_duplicate_keys():
    pairs = _parse_env_example()
    keys = [k for k, _ in pairs]
    duplicates = {k for k in keys if keys.count(k) > 1}
    assert not duplicates, f"Duplicate keys in .env.example: {sorted(duplicates)}"


def test_every_value_is_empty_or_placeholder():
    pairs = _parse_env_example()
    placeholder_re = re.compile(r'^<[^>]+>$')
    bad = [(k, v) for k, v in pairs if v and not placeholder_re.match(v)]
    assert not bad, f"Non-placeholder values in .env.example: {bad}"


def test_no_forbidden_substrings():
    text = ENV_EXAMPLE.read_text(encoding="utf-8", errors="replace")
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in text, f"Forbidden substring {forbidden!r} found in .env.example"


def test_contact_email_is_empty_placeholder():
    pairs = dict(_parse_env_example())
    assert pairs.get("CONTACT_EMAIL", "") == ""
