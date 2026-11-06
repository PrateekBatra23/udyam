"""Order tracker (section 2 module 4 + 14D), persisted in PostgreSQL.

Stages: Order placed -> KYC verified -> Provisioning -> Installation scheduled
-> Activated. Expected activation = order_date + max(typical_install_days)."""
import json
import uuid
from datetime import timedelta

import config
import db
from data_store import get_store

STAGES = ["Order placed", "KYC verified", "Provisioning",
          "Installation scheduled", "Activated"]


def _row_to_dict(r: dict) -> dict:
    bundle = r["bundle"] if isinstance(r["bundle"], list) else json.loads(r["bundle"])
    return {
        "order_id": r["order_id"],
        "bundle": bundle,
        "order_date": str(r["order_date"]),
        "expected_activation": str(r["expected_activation"]),
        "current_stage_index": r["current_stage_index"],
        "stages": STAGES,
    }


def create_order(bundle: list[str], order_date=None) -> dict:
    order_date = order_date or config.TODAY
    install_days = max([int(get_store().product(p).get("typical_install_days", 0))
                        for p in bundle] or [0])
    oid = "ORD-" + uuid.uuid4().hex[:8].upper()
    expected = order_date + timedelta(days=install_days)
    with db.cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO orders (order_id, bundle, order_date, expected_activation,
                                   current_stage_index)
               VALUES (%s, %s, %s, %s, 0)""",
            (oid, db.as_json(bundle), order_date, expected))
    return {"order_id": oid, "bundle": bundle, "order_date": str(order_date),
            "expected_activation": str(expected), "current_stage_index": 0, "stages": STAGES}


def get_order(order_id: str) -> dict | None:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
        r = cur.fetchone()
    return _row_to_dict(r) if r else None


def advance(order_id: str) -> dict | None:
    with db.cursor(commit=True) as cur:
        cur.execute(
            """UPDATE orders
                  SET current_stage_index = LEAST(current_stage_index + 1, %s)
                WHERE order_id = %s
            RETURNING *""",
            (len(STAGES) - 1, order_id))
        r = cur.fetchone()
    return _row_to_dict(r) if r else None
