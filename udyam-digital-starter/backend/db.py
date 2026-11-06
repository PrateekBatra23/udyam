"""PostgreSQL persistence for session state (orders, consent receipts).

Reference data (catalogue + registries) stays in memory in data_store — only
the things we WRITE live in Postgres, so state survives a backend restart.

Connection string via DATABASE_URL, e.g.
    postgresql://postgres:postgres@localhost:5432/udyam
A small connection pool is created lazily on first use.
"""
import os
import json
from contextlib import contextmanager

import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor

import config

DATABASE_URL = config.DATABASE_URL

_POOL: SimpleConnectionPool | None = None


def _pool() -> SimpleConnectionPool:
    global _POOL
    if _POOL is None:
        _POOL = SimpleConnectionPool(1, 10, dsn=DATABASE_URL)
    return _POOL


@contextmanager
def cursor(commit: bool = False):
    """Borrow a pooled connection and yield a dict-returning cursor."""
    conn = _pool().getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool().putconn(conn)


def init_db():
    """Create tables if absent. Called once on startup."""
    with cursor(commit=True) as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            bundle JSONB NOT NULL,
            order_date DATE NOT NULL,
            expected_activation DATE NOT NULL,
            current_stage_index INTEGER NOT NULL DEFAULT 0
        )""")
        for col in ("business_ref TEXT", "monthly_inr INTEGER", "one_time_inr INTEGER",
                    "contract_months INTEGER", "lines JSONB", "kyc_status TEXT",
                    "kyc_gstin_masked TEXT", "retention_until DATE", "consent_receipt_id TEXT"):
            cur.execute(f"ALTER TABLE orders ADD COLUMN IF NOT EXISTS {col}")
        cur.execute("""CREATE TABLE IF NOT EXISTS consent_receipts (
            receipt_id TEXT PRIMARY KEY,
            business_ref TEXT NOT NULL,
            timestamp_utc TIMESTAMPTZ NOT NULL,
            retention_until DATE NOT NULL,
            notice JSONB NOT NULL
        )""")
        cur.execute("ALTER TABLE consent_receipts ADD COLUMN IF NOT EXISTS withdrawn_at TIMESTAMPTZ")


def as_json(v) -> str:
    return json.dumps(v)
