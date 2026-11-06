"""DPDP helpers (section O8): PII masking + consent receipts (persisted in PG)."""
import uuid
from datetime import datetime, timedelta

import config
import db


def mask(identifier: str) -> str:
    """Show only the last 4 characters."""
    if not identifier:
        return ""
    s = str(identifier)
    return ("*" * max(len(s) - 4, 0)) + s[-4:]


def consent_notice() -> dict:
    return {
        "collected": ["GSTIN", "Udyam number", "address proof", "signatory ID"],
        "purpose": "Verify your business to activate the services you selected.",
        "retention_days": config.RETENTION_DAYS,
        "minimisation": "We collect KYC only after you accept a quote.",
        "rights": "You may withdraw consent and request deletion at any time.",
    }


def record_consent(business_ref: str) -> dict:
    rid = "CNS-" + uuid.uuid4().hex[:10].upper()
    now = datetime.utcnow()
    retention_until = (now + timedelta(days=config.RETENTION_DAYS)).date()
    notice = consent_notice()
    masked = mask(business_ref)
    with db.cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO consent_receipts (receipt_id, business_ref, timestamp_utc,
                                             retention_until, notice)
               VALUES (%s, %s, %s, %s, %s)""",
            (rid, masked, now, retention_until, db.as_json(notice)))
    return {"receipt_id": rid, "business_ref": masked,
            "timestamp_utc": now.isoformat() + "Z",
            "retention_until": retention_until.isoformat(), "notice": notice}


def get_consent(receipt_id: str) -> dict | None:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM consent_receipts WHERE receipt_id = %s", (receipt_id,))
        r = cur.fetchone()
    if not r:
        return None
    return {"receipt_id": r["receipt_id"], "business_ref": r["business_ref"],
            "timestamp_utc": str(r["timestamp_utc"]),
            "retention_until": str(r["retention_until"]), "notice": r["notice"]}
