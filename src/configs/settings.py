"""
Global project settings.

All application-wide configuration should live here.
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
# Database Configuration
# ---------------------------------------------------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://pc_builder:pc_builder123@localhost:5432/pc_builder"
)

