"""DPDP Act 2023 helpers (spec O8): PII masking, consent receipts persisted in
Postgres, consent withdrawal, and retention enforcement.

Design choices (also written up in the 1-page privacy note):
  * Consent BEFORE collection - KYC endpoints refuse requests without a live receipt.
  * Data minimisation - KYC is only reachable after a quote is accepted; uploaded
    images are OCR'd from a temp folder and deleted immediately, only the masked
    outcome is kept.
  * Masking - identifiers are shown last-4 only, in API responses, the UI and logs
    (a logging filter masks any GSTIN-shaped token, including in URLs).
  * Retention - RETENTION_DAYS (180); records past it are purged at startup.
  * Rights - a receipt can be withdrawn, which erases the KYC outcome linked to it.
"""
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

import config
import db

_GSTIN_IN_TEXT = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b")
_UDYAM_IN_TEXT = re.compile(r"\bUDYAM-[A-Z]{2}-\d{2}-\d{7}\b")
log = logging.getLogger("udyam.privacy")


def mask(identifier: str) -> str:
    """Show only the last 4 characters."""
    if not identifier:
        return ""
    s = str(identifier)
    return ("*" * max(len(s) - 4, 0)) + s[-4:]


def mask_text(text: str) -> str:
    """Mask every GSTIN / Udyam number found inside free text (log lines, URLs)."""
    text = _GSTIN_IN_TEXT.sub(lambda m: mask(m.group(0)), text)
    return _UDYAM_IN_TEXT.sub(lambda m: mask(m.group(0)), text)


class MaskingFilter(logging.Filter):
    """Attach to handlers/loggers so identifiers never reach the logs in clear."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # Mask in place and KEEP the args tuple: uvicorn's access formatter unpacks it.
            if isinstance(record.msg, str):
                record.msg = mask_text(record.msg)
            if isinstance(record.args, tuple):
                record.args = tuple(mask_text(a) if isinstance(a, str) else a for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: mask_text(v) if isinstance(v, str) else v
                               for k, v in record.args.items()}
        except Exception:
            pass
        return True


def install_log_masking():
    f = MaskingFilter()
    for name in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "udyam"):
        lg = logging.getLogger(name)
        lg.addFilter(f)
        for h in lg.handlers:
            h.addFilter(f)


def consent_notice() -> dict:
    return {
        "collected": ["GSTIN", "Udyam number", "address proof", "signatory ID"],
        "purpose": "Verify your business to activate the services you selected. "
                   "Nothing is used for marketing or shared with third parties.",
        "retention_days": config.RETENTION_DAYS,
        "minimisation": "We collect KYC only after you accept a quote, and your document "
                        "images are deleted as soon as they have been read.",
        "rights": "You may withdraw consent at any time; the verification record linked to "
                  "it is then erased.",
    }


def record_consent(business_ref: str) -> dict:
    rid = "CNS-" + uuid.uuid4().hex[:10].upper()
    now = datetime.now(timezone.utc)
    retention_until = (now + timedelta(days=config.RETENTION_DAYS)).date()
    notice = consent_notice()
    masked = mask(business_ref)
    with db.cursor(commit=True) as cur:
        cur.execute(
            """INSERT INTO consent_receipts (receipt_id, business_ref, timestamp_utc,
                                             retention_until, notice)
               VALUES (%s, %s, %s, %s, %s)""",
            (rid, masked, now, retention_until, db.as_json(notice)))
    log.info("consent recorded receipt=%s ref=%s", rid, masked)
    return {"receipt_id": rid, "business_ref": masked,
            "timestamp_utc": now.isoformat(),
            "retention_until": retention_until.isoformat(), "notice": notice,
            "withdrawn_at": None}


def get_consent(receipt_id: str) -> dict | None:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM consent_receipts WHERE receipt_id = %s", (receipt_id,))
        r = cur.fetchone()
    if not r:
        return None
    return {"receipt_id": r["receipt_id"], "business_ref": r["business_ref"],
            "timestamp_utc": r["timestamp_utc"].isoformat(),
            "retention_until": str(r["retention_until"]), "notice": r["notice"],
            "withdrawn_at": r["withdrawn_at"].isoformat() if r.get("withdrawn_at") else None}


def is_active(receipt_id: str | None) -> bool:
    """A receipt that exists, has not been withdrawn and has not expired."""
    if not receipt_id:
        return False
    r = get_consent(receipt_id)
    if not r or r["withdrawn_at"]:
        return False
    return r["retention_until"] >= str(datetime.now(timezone.utc).date())


def withdraw(receipt_id: str) -> dict | None:
    """DPDP right to withdraw: mark the receipt withdrawn and erase the KYC
    outcome stored against orders that were verified under it."""
    now = datetime.now(timezone.utc)
    with db.cursor(commit=True) as cur:
        cur.execute("UPDATE consent_receipts SET withdrawn_at = %s "
                    "WHERE receipt_id = %s AND withdrawn_at IS NULL RETURNING receipt_id",
                    (now, receipt_id))
        changed = cur.fetchone() is not None
        cur.execute("UPDATE orders SET kyc_status = NULL, kyc_gstin_masked = NULL "
                    "WHERE consent_receipt_id = %s", (receipt_id,))
        erased = cur.rowcount
    if not get_consent(receipt_id):
        return None
    log.info("consent withdrawn receipt=%s kyc_records_erased=%s", receipt_id, erased)
    return {"receipt_id": receipt_id, "withdrawn_at": now.isoformat(),
            "newly_withdrawn": changed, "kyc_records_erased": erased}


def purge_expired(today=None) -> dict:
    """Retention enforcement. `today` defaults to the real date for receipts and
    to config.TODAY for orders (whose dates live on the simulated demo clock)."""
    real_today = today or datetime.now(timezone.utc).date()
    with db.cursor(commit=True) as cur:
        cur.execute("UPDATE orders SET kyc_status = NULL, kyc_gstin_masked = NULL, "
                    "business_ref = NULL WHERE retention_until < %s AND "
                    "(kyc_status IS NOT NULL OR kyc_gstin_masked IS NOT NULL OR business_ref IS NOT NULL)",
                    (today or config.TODAY,))
        orders_cleared = cur.rowcount
        cur.execute("DELETE FROM consent_receipts WHERE retention_until < %s", (real_today,))
        receipts_deleted = cur.rowcount
    return {"orders_cleared": orders_cleared, "receipts_deleted": receipts_deleted}
