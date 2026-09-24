"""
Global project settings.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

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

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", 20))
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

MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RETRY_BACKOFF = int(os.getenv("BACKOFF_FACTOR", 2))

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
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

FUZZY_MATCH_THRESHOLD = float(os.getenv("FUZZY_MATCH_THRESHOLD", 0.90))

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

ENV = os.getenv("ENV", "development")

CORS_ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()
]

# Only when true may the rate-limit key function read the CF-Connecting-IP
# header. Phase 3 turns this on after OPS-02 firewalls the origin to
# Cloudflare ranges; until then the header is attacker-controlled, so the key
# function uses the socket address instead.
TRUST_CF_CONNECTING_IP = os.getenv("TRUST_CF_CONNECTING_IP", "false").lower() == "true"

# Rate limits (used by plan 01-05's slowapi limiter). The API must run as a
# single process - limiter counters are in memory, so extra workers multiply
# the effective limit.
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "300/minute")
RATE_LIMIT_IMAGES = os.getenv("RATE_LIMIT_IMAGES", "120/minute")
RATE_LIMIT_BUILDER = os.getenv("RATE_LIMIT_BUILDER", "60/minute")
RATE_LIMIT_SAVE_BUILD = os.getenv("RATE_LIMIT_SAVE_BUILD", "10/minute")

# Owner has not chosen a contact address yet (WEB-05). Empty is the clearly
# marked placeholder - never invent one. The About page shows a
# "contact address coming soon" note while this is empty.
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "")
