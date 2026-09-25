"""
Global project settings.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from limits import parse_many

# Load environment variables from .env
load_dotenv()


# ---------------------------------------------------------------------
# Blank-value handling (F2)
# ---------------------------------------------------------------------
# python-dotenv loads a blank `SOME_KEY=` line from a .env file as an empty
# string in the environment, not "unset" - so `os.getenv(name, default)`
# never sees the default; it returns "". A shipped .env.example with every
# value blank (the template a new deploy copies) would then feed "" into
# every setting below. For every setting except DATABASE_URL, blank means
# "use the default", applied consistently via this helper rather than ad hoc
# per line.

def _env_or_default(key: str, default: str) -> str:
    """`os.getenv(key, default)`, treating a present-but-blank/whitespace-only
    value the same as an absent one."""
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    return raw


def _bool_env(key: str, default: bool) -> bool:
    """A strict true/false env var: blank/unset means `default`; anything
    else that isn't exactly "true" or "false" (case/whitespace-insensitive)
    fails closed with a RuntimeError naming the variable, rather than the
    ambiguous `.lower() == "true"` pattern, under which a typo like "1" or
    "yes" silently means False."""
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized not in ("true", "false"):
        raise RuntimeError(
            f"{key} must be 'true' or 'false' (case/whitespace-insensitive); got {raw!r}."
        )
    return normalized == "true"


def _validated_rate_limit(key: str, default: str) -> str:
    """A rate-limit string (e.g. "300/minute"), blank-defaulted like
    `_env_or_default`, then validated eagerly at import with slowapi's own
    parser (`limits.parse_many`) - a bad value fails closed at startup,
    naming the variable, instead of 500ing every request that hits it."""
    value = _env_or_default(key, default)
    try:
        parse_many(value)
    except ValueError as exc:
        raise RuntimeError(f"{key} is not a valid rate limit string: {value!r} ({exc})") from exc
    return value

# ---------------------------------------------------------------------
# Project Paths
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EXPORT_DIR = DATA_DIR / "exports"
CACHE_DIR = DATA_DIR / "cache"
LOG_DIR = PROJECT_ROOT / "logs"

# ---------------------------------------------------------------------
# HTTP Configuration
# ---------------------------------------------------------------------

REQUEST_TIMEOUT = int(_env_or_default("REQUEST_TIMEOUT", "20"))
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

# ---------------------------------------------------------------------
# Retry Configuration
# ---------------------------------------------------------------------

MAX_RETRIES = int(_env_or_default("MAX_RETRIES", "3"))
RETRY_BACKOFF = int(_env_or_default("BACKOFF_FACTOR", "2"))

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

LOG_LEVEL = _env_or_default("LOG_LEVEL", "INFO")
LOG_FILE = LOG_DIR / "pc_builder.log"

# ---------------------------------------------------------------------
# AI / LLM Configuration
# ---------------------------------------------------------------------

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")

# ---------------------------------------------------------------------
# Matching Pipeline Configuration
# ---------------------------------------------------------------------

FUZZY_MATCH_THRESHOLD = float(_env_or_default("FUZZY_MATCH_THRESHOLD", "0.90"))

# ---------------------------------------------------------------------
# Database Configuration
# ---------------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")


def require_database_url() -> str:
    """Return DATABASE_URL, or fail closed if it is unset/blank.

    Never raises at import time (scripts such as the Phase 1 benchmark import
    settings on machines with no database) - callers that need a live DB call
    this explicitly. The error names the missing variable only, never a value.
    """
    if not DATABASE_URL or not DATABASE_URL.strip():
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and set it.")
    return DATABASE_URL

# ---------------------------------------------------------------------
# Runtime environment / web security
# ---------------------------------------------------------------------

_ALLOWED_ENVS = ("development", "production")
_env_raw = _env_or_default("ENV", "development")
ENV = _env_raw.strip().lower()
if ENV not in _ALLOWED_ENVS:
    raise RuntimeError(
        f"ENV must be one of {_ALLOWED_ENVS} (case/whitespace-insensitive); "
        f"got {_env_raw!r}."
    )

CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()
]

# Only when true may the rate-limit key function read the CF-Connecting-IP
# header. Phase 3 turns this on after OPS-02 firewalls the origin to
# Cloudflare ranges; until then the header is attacker-controlled, so the key
# function uses the socket address instead.
TRUST_CF_CONNECTING_IP = _bool_env("TRUST_CF_CONNECTING_IP", False)

# Rate limits (used by plan 01-05's slowapi limiter). The API must run as a
# single process - limiter counters are in memory, so extra workers multiply
# the effective limit.
RATE_LIMIT_ENABLED = _bool_env("RATE_LIMIT_ENABLED", True)
RATE_LIMIT_DEFAULT = _validated_rate_limit("RATE_LIMIT_DEFAULT", "300/minute")
RATE_LIMIT_IMAGES = _validated_rate_limit("RATE_LIMIT_IMAGES", "120/minute")
RATE_LIMIT_BUILDER = _validated_rate_limit("RATE_LIMIT_BUILDER", "60/minute")
RATE_LIMIT_SAVE_BUILD = _validated_rate_limit("RATE_LIMIT_SAVE_BUILD", "10/minute")

# Owner has not chosen a contact address yet (WEB-05). Empty is the clearly
# marked placeholder - never invent one. The About page shows a
# "contact address coming soon" note while this is empty.
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "")
