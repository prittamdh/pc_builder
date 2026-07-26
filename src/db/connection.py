import os
from sqlalchemy import create_engine

from configs.settings import DATABASE_URL

db_url = DATABASE_URL

import sqlalchemy

# Convert psycopg3 dialect scheme to psycopg2 for SQLAlchemy 1.4 or missing driver
if "postgresql+psycopg://" in db_url:
    if sqlalchemy.__version__.startswith("1."):
        db_url = db_url.replace("postgresql+psycopg://", "postgresql+psycopg2://")
    else:
        try:
            import psycopg  # noqa
        except ImportError:
            db_url = db_url.replace("postgresql+psycopg://", "postgresql+psycopg2://")

# Inside Docker container, fallback localhost:5432 to postgres:5432
if os.path.exists("/.dockerenv") and "@localhost:5432" in db_url:
    db_url = db_url.replace("@localhost:5432", "@postgres:5432")

engine = create_engine(
    db_url,
    echo=False,
    pool_pre_ping=True,
)