from __future__ import annotations
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from app.db import engine


def _add_column(table: str, name: str, definition: str) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns(table)}
    if name in columns:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
    except SQLAlchemyError:
        # Web and worker may start together. Ignore only when the other process
        # has already created the same column; otherwise surface the real error.
        columns = {column["name"] for column in inspect(engine).get_columns(table)}
        if name not in columns:
            raise


def run_lightweight_migrations() -> None:
    """Additive migrations for upgrades from v0.3.x without deleting existing data."""
    tables = set(inspect(engine).get_table_names())
    if "campaigns" in tables:
        _add_column("campaigns", "landing_body", "TEXT DEFAULT ''")
        _add_column("campaigns", "highlights", "TEXT DEFAULT ''")
        _add_column("campaigns", "cover_image", "VARCHAR(500)")
        _add_column("campaigns", "product_mode", "VARCHAR(20) DEFAULT 'free'")
        _add_column("campaigns", "price_amount", "INTEGER DEFAULT 0")
        _add_column("campaigns", "checkout_url", "VARCHAR(700)")
        _add_column("campaigns", "payment_instructions", "TEXT DEFAULT ''")
        _add_column("campaigns", "purchase_button_label", "VARCHAR(80) DEFAULT 'BELI SEKARANG'")
    if "leads" in tables:
        _add_column("leads", "payment_status", "VARCHAR(30) DEFAULT 'not_required'")
        _add_column("leads", "payment_amount", "INTEGER DEFAULT 0")
        _add_column("leads", "paid_at", "DATETIME" if engine.dialect.name == "sqlite" else "TIMESTAMP WITH TIME ZONE")
