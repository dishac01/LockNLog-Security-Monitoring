"""SQLite additive migrations for evolving models."""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.extensions import db


def ensure_intelligence_schema() -> None:
    """Add intelligence columns to `logs` if missing (existing SQLite DBs)."""
    bind = db.engine
    insp = inspect(bind)
    tables = insp.get_table_names()
    if "logs" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("logs")}
    alters: list[str] = []
    if "anomaly_score" not in cols:
        alters.append("ALTER TABLE logs ADD COLUMN anomaly_score REAL")
    if "risk_score" not in cols:
        alters.append("ALTER TABLE logs ADD COLUMN risk_score REAL")
    if "risk_band" not in cols:
        alters.append("ALTER TABLE logs ADD COLUMN risk_band VARCHAR(16)")
    if not alters:
        return
    with bind.begin() as conn:
        for stmt in alters:
            conn.execute(text(stmt))


def ensure_access_request_schema() -> None:
    """
    Access requests are a new table. `db.create_all()` will create it for new DBs,
    but older SQLite DB files may already exist; in that case, create the table
    if missing.
    """
    bind = db.engine
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "access_requests" in tables:
        return
    # Create missing tables (idempotent for other existing tables).
    db.create_all()


def ensure_asset_inventory_schema() -> None:
    """Add unified inventory columns to `assets` if missing (SQLite additive migration)."""
    bind = db.engine
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    if "assets" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("assets")}

    alters: list[str] = []
    if "asset_type" not in cols:
        alters.append("ALTER TABLE assets ADD COLUMN asset_type VARCHAR(64)")
    if "transaction_volume" not in cols:
        alters.append("ALTER TABLE assets ADD COLUMN transaction_volume REAL")
    if "avg_transaction_amount" not in cols:
        alters.append("ALTER TABLE assets ADD COLUMN avg_transaction_amount REAL")
    if "data_types" not in cols:
        alters.append("ALTER TABLE assets ADD COLUMN data_types TEXT")
    if "employee_count" not in cols:
        alters.append("ALTER TABLE assets ADD COLUMN employee_count INTEGER")
    if "ip_address" not in cols:
        alters.append("ALTER TABLE assets ADD COLUMN ip_address VARCHAR(64)")
    if "exposed_ports" not in cols:
        alters.append("ALTER TABLE assets ADD COLUMN exposed_ports TEXT")
    if "risk_score" not in cols:
        alters.append("ALTER TABLE assets ADD COLUMN risk_score REAL")
    if "last_activity" not in cols:
        alters.append("ALTER TABLE assets ADD COLUMN last_activity DATETIME")

    if not alters:
        return
    with bind.begin() as conn:
        for stmt in alters:
            conn.execute(text(stmt))
