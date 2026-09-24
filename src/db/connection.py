import os
from sqlalchemy import create_engine

from configs.settings import require_database_url

# Fails closed with a clear message naming DATABASE_URL when it is unset/blank,
# instead of passing None/"" into create_engine() and getting an opaque TypeError or
# sqlalchemy.exc.ArgumentError with no mention of the missing setting. Every script and
# DAG that imports db.connection (directly or via db.session) needs this, not only
# src/api/main.py.
db_url = require_database_url()

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