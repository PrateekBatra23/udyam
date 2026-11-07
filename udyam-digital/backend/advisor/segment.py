"""Infer segment from registry fields (section O1).

The registries carry no segment field, so this is a heuristic and is returned as
a CONFIRMABLE guess - never ground truth. Signals, strongest first:
  1. Udyam `nic_description` (a business type such as 'Dental clinic'), mapped to
     a segment using the type->segment table DERIVED from smb_leads.csv.
  2. Business-type words in the legal/trade name.
  3. Udyam `major_activity` / constitution broad class.
"""
from data_store import get_store, _norm

_KEYWORDS = {
    "prof":  ["clinic", "dental", "diagnostic", "lab", "law", "legal", "associates", "chartered",
              "ca firm", "coaching", "classes", "academy", "tuition", "consult", "architect",
              "studio", "insurance", "advisors", "real estate", "realty", "travel", "tours",
              "physio", "hospital"],
    "multi": ["chain", "group", "hotel", "restaurant", "outlets", "franchise", "gym",
              "pre school", "preschool", "stores", "stays", "retail", "fashions", "mart"],
    "mfg":   ["manufactur", "factory", "textile", "auto parts", "auto-parts", "machin",
              "fabricat", "industries", "plant", "foundry", "packaging", "moulding",
              "printing", "press", "workshop", "furniture", "food processing", "components",
              "engineering", "auto"],
    "micro": ["kirana", "salon", "pharmacy", "bakery", "grocery", "shop", "store", "sweet",
              "boutique", "optician", "stationery", "hardware", "mobile repair", "cafe"],
}


def infer_segment(gstin_row: dict | None, udyam_row: dict | None) -> dict:
    """Returns {segment, confidence, basis}. confidence in {high, medium, low}."""
    store = get_store()
    nic = _norm((udyam_row or {}).get("nic_description"))
    if nic and nic in store.type_segment:
        return {"segment": store.type_segment[nic], "confidence": "high",
                "basis": f"registered activity: {(udyam_row or {}).get('nic_description')}"}

    text = _norm(" ".join(str(x) for x in [
        (gstin_row or {}).get("trade_name", ""), (gstin_row or {}).get("legal_name", "")]))
    for seg in ("prof", "multi", "mfg", "micro"):
        for kw in _KEYWORDS[seg]:
            if _norm(kw) in text:
                return {"segment": seg, "confidence": "medium", "basis": f"name contains '{kw}'"}

    activity = str((udyam_row or {}).get("major_activity", "")).lower()
    if "manufactur" in activity:
        return {"segment": "mfg", "confidence": "low", "basis": "Udyam major activity: manufacturing"}
    constitution = str((gstin_row or {}).get("constitution", "")).lower()
    if "limited liability" in constitution or "private limited" in constitution:
        return {"segment": "prof", "confidence": "low", "basis": f"constitution: {constitution}"}
    return {"segment": "micro", "confidence": "low", "basis": "default (no signal found)"}
