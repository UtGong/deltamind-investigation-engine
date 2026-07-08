from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_directory(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return

    database_path = url.database
    if not database_path:
        return

    sqlite_path = Path(database_path)
    if not sqlite_path.is_absolute():
        sqlite_path = Path.cwd() / sqlite_path

    sqlite_path.parent.mkdir(parents=True, exist_ok=True)


def build_engine():
    settings = get_settings()
    _ensure_sqlite_directory(settings.database_url)

    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


engine = build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


def check_database_connection() -> dict:
    settings = get_settings()

    try:
        with engine.connect() as connection:
            version = connection.execute(text("SELECT version()")).scalar_one()
            vector_enabled = connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_extension
                        WHERE extname = 'vector'
                    )
                    """
                )
            ).scalar_one()

        return {
            "database_backend": settings.database_backend,
            "database_url_configured": bool(settings.database_url),
            "connected": True,
            "postgres_version": version,
            "pgvector_enabled": bool(vector_enabled),
            "error": None,
        }
    except Exception as error:
        return {
            "database_backend": settings.database_backend,
            "database_url_configured": bool(settings.database_url),
            "connected": False,
            "postgres_version": None,
            "pgvector_enabled": False,
            "error": str(error),
        }
