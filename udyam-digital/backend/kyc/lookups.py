"""Registry lookups. The TYPED identifier (from onboarding) is the source of
truth; OCR output is only cross-checked against it (section O4).

`resolve_gstin_from_ocr` is only used when NO typed GSTIN exists (the OCR-only
batch/stress view): it repairs a noisy OCR read to a registry entry, but never
trusts a registry hit that the document's own business name does not back up.
"""
from collections import Counter
from functools import lru_cache

from data_store import get_store
from rules import identifiers
from kyc import names


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


# ------------------------------------------------------------ derived tables
@lru_cache(maxsize=1)
def state_code_map() -> dict:
    """GSTIN state code -> state name, DERIVED from the registry (modal state
    per 2-digit prefix) rather than hard-coded."""
    by_code: dict[str, Counter] = {}
    for g, row in get_store().gstin.items():
        by_code.setdefault(g[:2], Counter())[row["state"]] += 1
    return {c: cnt.most_common(1)[0][0] for c, cnt in by_code.items()}


@lru_cache(maxsize=1)
def known_states() -> list:
    return sorted({r["state"] for r in get_store().gstin.values()} |
                  {r["state"] for r in get_store().udyam.values()})


@lru_cache(maxsize=1)
def _name_index() -> dict:
    idx: dict[str, list] = {}
    for g, row in get_store().gstin.items():
        for n in {row["trade_name"], names.split_proprietor(row["legal_name"])[1]}:
            idx.setdefault(names.normalise(n), []).append(g)
    return idx


def lev(a: str, b: str) -> int:
    """Levenshtein distance (small strings)."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def resolve_gstin_from_ocr(candidates: list, name_hints: list) -> dict:
    """Repair a noisy OCR'd GSTIN to a registry entry.

    Order: (1) checksum/confusion repair that lands in the registry;
           (2) nearest registry GSTIN among businesses whose NAME matches the
               document's names (name-corroborated, distance <= 4);
           (3) global nearest, distance <= 2 and unique.
    Returns {"gstin", "method", "distance", "name_corroborated"} or
    {"gstin": None}."""
    known = set(get_store().gstin)
    cands = [c for c in dict.fromkeys(candidates) if 12 <= len(c) <= 17]
    if not cands:
        return {"gstin": None}

    for c in cands:
        fixed, corrected = identifiers.correct_gstin_ocr(c, known)
        if fixed in known:
            return {"gstin": fixed, "method": "confusion-repair" if corrected else "exact",
                    "distance": lev(c, fixed), "name_corroborated": None}

    hints = [h for h in name_hints if h]
    pool = set()
    idx = _name_index()
    for h in hints:
        pool.update(idx.get(names.normalise(h), []))
    if pool:
        best = min(((lev(c, g), g) for c in cands for g in pool), default=None)
        if best and best[0] <= 4:
            return {"gstin": best[1], "method": "name-corroborated-nearest",
                    "distance": best[0], "name_corroborated": True}

    scored = sorted((lev(c, g), g) for c in cands for g in known)
    if scored and scored[0][0] <= 2 and (len(scored) == 1 or scored[1][0] > scored[0][0]):
        return {"gstin": scored[0][1], "method": "global-nearest",
                "distance": scored[0][0], "name_corroborated": False}
    return {"gstin": None}
