"""Lightweight, idempotent startup schema patches for existing SQLite databases.

This prototype has no full migration framework (e.g. Alembic) and relies on
Base.metadata.create_all() for fresh databases — which only creates tables
that don't exist yet and never alters existing ones. When a model's schema
changes in a way create_all() can't express (renamed/added columns), a patch
must be added here so upgrades don't break databases created by an older
version of the app.
"""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def run_startup_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    if "approvals" in table_names:
        columns = {c["name"] for c in inspector.get_columns("approvals")}
        if "head_id" in columns and "actor_id" not in columns:
            # approvals.head_id was renamed to actor_id so the table could also
            # record champion-triggered revisions, not just head decisions.
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE approvals RENAME COLUMN head_id TO actor_id"))

    if "resources" in table_names:
        columns = {c["name"] for c in inspector.get_columns("resources")}
        if "rate" not in columns:
            # resources.rate (cost per unit, set by PM) was added later.
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE resources ADD COLUMN rate REAL NOT NULL DEFAULT 0"))
