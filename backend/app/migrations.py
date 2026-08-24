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
        if "team_lead_id" not in columns:
            # resources.team_lead_id (owner of the specialization, role "teamlead") was added later.
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE resources ADD COLUMN team_lead_id INTEGER REFERENCES employees(id)"))

    if "initiatives" in table_names:
        columns = {c["name"] for c in inspector.get_columns("initiatives")}
        if "approval_stage" not in columns:
            # initiatives.approval_stage (multi-step approval chain: head -> TeamLeads)
            # was added later. Existing rows default to "head": already-approved
            # initiatives ignore it (is_approved gates them), and not-yet-approved
            # ones correctly need a (re-)decision from the head, same as before.
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE initiatives ADD COLUMN approval_stage TEXT NOT NULL DEFAULT 'head'"))

    if "pending_approvers" in table_names:
        columns = {c["name"] for c in inspector.get_columns("pending_approvers")}
        if "status" not in columns:
            # pending_approvers.status ("pending"/"approved") was added later so a
            # TeamLead's own approved rows can be kept (not deleted) for visibility
            # in "Согласованные" while peers are still deciding.
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE pending_approvers ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'"))

    if "notifications" in table_names:
        columns = {c["name"] for c in inspector.get_columns("notifications")}
        if "type" not in columns:
            # notifications.type ("info"/"reminder") was added later to tell
            # apart the weekly time-logging reminder from regular notifications.
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE notifications ADD COLUMN type TEXT NOT NULL DEFAULT 'info'"))
