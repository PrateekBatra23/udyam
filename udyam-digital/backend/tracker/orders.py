"""Order tracker (section 2 module 4 + 14D), persisted in PostgreSQL.

Stages: Order placed -> KYC verified -> Provisioning -> Installation scheduled
-> Activated. Expected activation = order_date + max(typical_install_days)
across the bundle (spec 14D). Intermediate stage ETAs are a linear split of that
window (assumption recorded in DEV_NOTES)."""
import json
import math
import uuid
from datetime import timedelta

import config
import db
from data_store import get_store

STAGES = ["Order placed", "KYC verified", "Provisioning",
          "Installation scheduled", "Activated"]


def _etas(order_date, install_days: int) -> list[str]:
    """Target date per stage: placed d0, KYC d1, provisioning ~40%, install ~70%, live d=install."""
    d = max(int(install_days), 1)
    offs = [0, min(1, d), math.ceil(d * 0.4), math.ceil(d * 0.7), d]
    return [str(order_date + timedelta(days=o)) for o in offs]


def _row_to_dict(r: dict) -> dict:
    bundle = r["bundle"] if isinstance(r["bundle"], list) else json.loads(r["bundle"])
    store = get_store()
    install = max([int(store.product(p).get("typical_install_days", 0)) for p in bundle] or [0])
    od = r["order_date"]
    lines = r.get("lines")
    if isinstance(lines, str):
        lines = json.loads(lines)
    return {
        "order_id": r["order_id"],
        "bundle": bundle,
        "lines": lines or [],
        "order_date": str(od),
        "expected_activation": str(r["expected_activation"]),
        "current_stage_index": r["current_stage_index"],
        "stages": STAGES,
        "stage_eta": _etas(od, install),
        "monthly_inr": r.get("monthly_inr"),
        "one_time_inr": r.get("one_time_inr"),
        "contract_months": r.get("contract_months"),
        "kyc_status": r.get("kyc_status"),
        "kyc_gstin_masked": r.get("kyc_gstin_masked"),
        "business_ref": r.get("business_ref"),
        "retention_until": str(r["retention_until"]) if r.get("retention_until") else None,
    }


def create_order(bundle: list[str], quote: dict | None = None, business_ref: str = "",
                 order_date=None) -> dict:
    order_date = order_date or config.TODAY
    store = get_store()
    install_days = max([int(store.product(p).get("typical_install_days", 0))
                        for p in bundle] or [0])
    oid = "ORD-" + uuid.uuid4().hex[:8].upper()
    expected = order_date + timedelta(days=install_days)
    retention_until = order_date + timedelta(days=config.RETENTION_DAYS)
    q = quote or {}
    lines = [{"product_id": l["product_id"], "name": l["name"], "qty": l["qty"],
              "monthly_inr": l["monthly_inr"], "one_time_inr": l["one_time_inr"]}
             for l in q.get("lines", [])]
    with db.cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO orders (order_id, bundle, order_date, expected_activation,
                                   current_stage_index, business_ref, monthly_inr,
                                   one_time_inr, contract_months, lines, retention_until)
               VALUES (%s, %s, %s, %s, 0, %s, %s, %s, %s, %s, %s)""",
            (oid, db.as_json(bundle), order_date, expected, business_ref,
             q.get("monthly_inr"), q.get("one_time_inr"), q.get("contract_months"),
             db.as_json(lines), retention_until))
    return get_order(oid)


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


def record_kyc(order_id: str, decision: str, gstin_masked: str | None,
               consent_receipt_id: str | None = None):
    """Store the (masked) KYC outcome. APPROVE moves the order to 'KYC verified';
    REVIEW/REJECT leave it at 'Order placed' for follow-up."""
    with db.cursor(commit=True) as cur:
        cur.execute(
            """UPDATE orders
                  SET kyc_status = %s, kyc_gstin_masked = %s, consent_receipt_id = %s,
                      current_stage_index = CASE WHEN %s = 'APPROVE'
                                                 THEN GREATEST(current_stage_index, 1)
                                                 ELSE current_stage_index END
                WHERE order_id = %s""",
            (decision, gstin_masked, consent_receipt_id, decision, order_id))
