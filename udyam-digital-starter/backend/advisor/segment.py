"""Infer segment from registry fields (section O1). Keyword heuristic, returned
as a CONFIRMABLE guess — never ground truth. The frontend confirms it."""

_KEYWORDS = {
    "prof":  ["clinic", "dental", "hospital", "ca ", "chartered", "law", "legal",
              "coaching", "tuition", "consult", "architect", "design studio",
              "accounting", "doctor", "diagnostic"],
    "multi": ["chain", "multi", "stores", "outlets", "restaurant", "franchise",
              "retail chain", "branches"],
    "mfg":   ["manufactur", "unit", "factory", "textile", "auto-parts", "auto parts",
              "machin", "fabricat", "industries", "plant", "foundry"],
    "micro": ["kirana", "salon", "pharmacy", "bakery", "grocery", "shop", "store",
              "cafe", "stall", "boutique", "parlour", "parlor"],
}


def infer_segment(gstin_row: dict | None, udyam_row: dict | None) -> dict:
    """Returns {segment, confidence, basis}. confidence in {high, medium, low}."""
    text = " ".join(str(x).lower() for x in [
        (gstin_row or {}).get("trade_name", ""),
        (gstin_row or {}).get("legal_name", ""),
        (udyam_row or {}).get("major_activity", ""),
        (udyam_row or {}).get("nic_description", ""),
    ])
    for seg, kws in _KEYWORDS.items():
        for kw in kws:
            if kw in text:
                return {"segment": seg, "confidence": "medium", "basis": kw.strip()}

    # fall back to Udyam major_activity broad class
    activity = str((udyam_row or {}).get("major_activity", "")).lower()
    if "manufactur" in activity:
        return {"segment": "mfg", "confidence": "low", "basis": "major_activity"}
    if "trading" in activity:
        return {"segment": "multi", "confidence": "low", "basis": "major_activity"}
    return {"segment": "micro", "confidence": "low", "basis": "default"}
