from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=10)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()

# create_all never alters existing tables, so columns added after the first deploy go here.
_ADDED_COLUMNS = {
    "generation_jobs": [
        ("brief", "JSON"),
        ("full_script", "JSON"),
        ("review_status", "VARCHAR DEFAULT 'pending'"),
        ("review_notes", "TEXT"),
        ("delivered_at", "TIMESTAMPTZ"),
        ("delivery_log", "TEXT"),
    ],
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models_db  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            for name, ddl in columns:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {ddl}"))
