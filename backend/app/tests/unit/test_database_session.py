import importlib
from pathlib import Path

from sqlalchemy import inspect

import app.core.config as config_module
import app.db.session as session_module


def test_build_engine_falls_back_to_sqlite_when_database_url_is_blank(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DATABASE_URL", "")

    config_module.get_settings.cache_clear()
    reloaded_session_module = importlib.reload(session_module)

    engine = reloaded_session_module.build_engine()

    assert engine.url.get_backend_name() == "sqlite"
    assert engine.url.database == "./data/deltamind_local.sqlite3"
    assert Path("data").is_dir()


def test_initialize_database_creates_sqlite_tables(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("DATABASE_URL", "")

    config_module.get_settings.cache_clear()
    reloaded_session_module = importlib.reload(session_module)

    reloaded_session_module.initialize_database()

    inspector = inspect(reloaded_session_module.engine)
    assert inspector.has_table("cases")
