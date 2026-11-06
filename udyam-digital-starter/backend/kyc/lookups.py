"""Registry lookups. The TYPED identifier (from onboarding) is the source of
truth; OCR output is only cross-checked against it (section O4)."""
from data_store import get_store


def gstin_status(gstin: str) -> dict:
    row = get_store().gstin_lookup(gstin)
    if not row:
        return {"found": False}
    return {"found": True, "status": row.get("status"),
            "legal_name": row.get("legal_name"), "trade_name": row.get("trade_name"),
            "state": row.get("state"),
            "principal_place_of_business": row.get("principal_place_of_business"),
            "constitution": row.get("constitution")}


def udyam_status(udyam: str) -> dict:
    row = get_store().udyam_lookup(udyam)
    if not row:
        return {"found": False}
    return {"found": True, "enterprise_name": row.get("enterprise_name"),
            "enterprise_type": row.get("enterprise_type"),
            "major_activity": row.get("major_activity"),
            "state": row.get("state"), "city": row.get("city")}
