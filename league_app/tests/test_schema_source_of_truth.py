"""Regression tests for review finding M10 — one source of truth for the schema.

``main.lifespan`` used to call ``Base.metadata.create_all`` on every start
while Alembic managed the same schema independently.  ``create_all`` does
not alter existing tables and never stamps an Alembic revision, so a
production database created that way silently ignored every later model
change *and* could not be migrated afterwards (``alembic upgrade head``
would try to create tables that already exist).

The application no longer touches the schema: ``alembic upgrade head`` is
the one way to create or update it.  These tests pin both halves of that
contract:

* app startup creates no tables at all;
* a fresh ``alembic upgrade head`` against an empty database produces
  exactly the schema the models describe (what ``create_all`` would have
  built), and stamps a revision — so the migrations cannot drift away from
  the models unnoticed.

The test suite's own use of ``create_all`` (``league_app/tests/conftest.py``)
is a different, legitimate case: a throwaway in-memory database recreated
per run, never migrated.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from league_app.database import Base
from league_app.main import lifespan

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


def _schema_of(sync_url: str) -> dict[str, dict[str, tuple[str, bool]]]:
    """Tables → columns → (type, nullable), ignoring alembic's own table."""
    engine = create_engine(sync_url)
    try:
        inspector = inspect(engine)
        return {
            table: {
                column["name"]: (type(column["type"]).__name__, bool(column["nullable"]))
                for column in inspector.get_columns(table)
            }
            for table in sorted(inspector.get_table_names())
            if table != "alembic_version"
        }
    finally:
        engine.dispose()


def _stamped_revision(sync_url: str) -> str | None:
    engine = create_engine(sync_url)
    try:
        inspector = inspect(engine)
        if "alembic_version" not in inspector.get_table_names():
            return None
        with engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).first()
        return row[0] if row else None
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# The app does not create tables
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_startup_creates_no_tables(tmp_path, monkeypatch):
    """Running the lifespan against an empty database leaves it empty."""
    db_path = tmp_path / "startup.db"
    url = f"sqlite+aiosqlite:///{db_path}"

    from league_app import main as main_module
    from league_app.database import get_async_engine

    monkeypatch.setattr(
        main_module, "get_async_engine", lambda: get_async_engine(url),
    )

    async with lifespan(main_module.app):
        pass

    # The file may exist (SQLite creates it on connect) but must have no tables.
    assert _schema_of(f"sqlite:///{db_path}") == {}
    assert _stamped_revision(f"sqlite:///{db_path}") is None


def test_create_all_is_not_referenced_by_the_app():
    """Belt and braces: no production code path *calls* create_all.

    Matches the call form (``metadata.create_all(``) so that prose
    explaining why it is gone does not trip the check.
    """
    app_sources = [
        path for path in (REPO_ROOT / "league_app").rglob("*.py")
        if "tests" not in path.parts
    ]
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in app_sources
        if "metadata.create_all(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"create_all is back in {offenders}"


# ---------------------------------------------------------------------------
# Alembic is the source of truth
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not ALEMBIC_INI.is_file(), reason="alembic.ini not found next to the repo"
)
def test_alembic_upgrade_head_matches_the_models(tmp_path):
    """`alembic upgrade head` on an empty DB == what the models describe.

    This is the drift guard: add a column to a model without a migration
    (or write a migration that does not match the model) and this fails.
    Run on its own with `make check-migrations`.
    """
    migrated = tmp_path / "migrated.db"
    from_models = tmp_path / "from_models.db"

    env = dict(os.environ)
    env["ASYNC_DATABASE_URL"] = f"sqlite+aiosqlite:///{migrated}"
    env.setdefault("SECRET_KEY", "schema-test")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, (
        f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"
    )

    engine = create_engine(f"sqlite:///{from_models}")
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    migrated_schema = _schema_of(f"sqlite:///{migrated}")
    model_schema = _schema_of(f"sqlite:///{from_models}")

    assert set(migrated_schema) == set(model_schema), (
        "tables differ between migrations and models"
    )
    for table in sorted(model_schema):
        assert migrated_schema[table] == model_schema[table], (
            f"columns of '{table}' differ between migrations and models"
        )

    # ...and a database built this way is migratable: it carries a revision.
    assert _stamped_revision(f"sqlite:///{migrated}") is not None
