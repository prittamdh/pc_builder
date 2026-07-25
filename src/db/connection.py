import os
from sqlalchemy import create_engine

from configs.settings import DATABASE_URL

db_url = DATABASE_URL

# Fallback for environments without psycopg 3 driver installed (e.g. Airflow container with psycopg2)
if "psycopg" in db_url and "+psycopg2" not in db_url:
    try:
        import psycopg  # noqa
    except ImportError:
        db_url = db_url.replace("postgresql+psycopg://", "postgresql+psycopg2://")

# Inside Docker container, fallback localhost:5432 to postgres:5432 if host is unreachable
if os.path.exists("/.dockerenv") and "@localhost:5432" in db_url:
    db_url = db_url.replace("@localhost:5432", "@postgres:5432")

engine = create_engine(
    db_url,
    echo=False,
    pool_pre_ping=True,
)