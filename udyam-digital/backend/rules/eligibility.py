"""Section 5 eligibility engine.

A Profile is the minimum the advisor needs to reason about eligibility:
  segment, city_tier (int 1/2), employee_count (int), num_sites (int),
  has_active_gstin (bool).

`eligible_products(profile)` returns the set of product_ids sellable to that
profile IGNORING dependencies (requires_one_of), because dependencies are about
bundle composition, not the product in isolation. `validate_bundle` then checks
dependencies against the chosen bundle.
"""
from dataclasses import dataclass
from data_store import get_store


@dataclass
class Profile:
    segment: str = "micro"          # micro | prof | multi | mfg
    city_tier: int = 2
    employee_count: int = 1
    num_sites: int = 1
    has_active_gstin: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        return cls(
            segment=d.get("segment", "micro"),
            city_tier=int(d.get("city_tier", 2)),
            employee_count=int(d.get("employee_count", 1)),
            num_sites=int(d.get("num_sites", 1)),
            has_active_gstin=bool(d.get("has_active_gstin", False)),
        )


def _tiers(p: dict) -> set[int]:
    return {int(t) for t in str(p["available_city_tiers"]).split(";") if t.strip()}


def _int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def product_eligible(profile: Profile, pid: str) -> tuple[bool, str]:
    """Checks the standalone gates (tier, size, GSTIN). Not dependencies."""
    p = get_store().product(pid)
    if p is None:
        return False, f"{pid}: unknown product"
    if profile.city_tier not in _tiers(p):
        return False, f"{pid}: not sold in city tier {profile.city_tier}"
    if profile.employee_count < _int(p.get("min_employees"), 0):
        return False, f"{pid}: needs >= {p['min_employees']} employees"
    if profile.num_sites < _int(p.get("min_sites"), 0):
        return False, f"{pid}: needs >= {p['min_sites']} sites"
    if str(p.get("requires_gstin")).strip().upper() == "Y" and not profile.has_active_gstin:
        return False, f"{pid}: requires an active GSTIN"
    return True, "ok"


def eligible_products(profile: Profile) -> list[str]:
    """Candidate set to hand the LLM (section O2 candidate-set constraining)."""
    out = []
    for pid in get_store().products:
        ok, _ = product_eligible(profile, pid)
        if ok:
            out.append(pid)
    return out


def _requires_one_of(pid: str) -> list[str]:
    p = get_store().product(pid)
    if p is None:                    # unknown product id (e.g. invented by a model): no dependencies
        return []
    raw = p.get("requires_one_of")
    if not raw or str(raw) == "nan":
        return []
    return [x for x in str(raw).split("|") if x.strip()]


def validate_bundle(profile: Profile, bundle: list[str]) -> tuple[bool, list[str]]:
    """Full check incl. dependencies. Returns (ok, reasons_for_failures)."""
    reasons = []
    bundle_set = set(bundle)
    for pid in bundle:
        ok, why = product_eligible(profile, pid)
        if not ok:
            reasons.append(why)
            continue
        dep = _requires_one_of(pid)
        if dep and not (bundle_set & set(dep)):
            reasons.append(f"{pid}: needs one of {'|'.join(dep)} in the bundle")
    return (len(reasons) == 0), reasons


def strip_ineligible(profile: Profile, bundle: list[str]) -> tuple[list[str], list[str]]:
    """Backstop used after the LLM: remove anything that fails, return
    (clean_bundle, removed_with_reasons). Iterates until stable because removing
    a base product can invalidate a dependent one."""
    removed = []
    cur = list(dict.fromkeys(bundle))  # dedupe, keep order
    changed = True
    while changed:
        changed = False
        ok, _ = validate_bundle(profile, cur)
        if ok:
            break
        for pid in list(cur):
            good, why = product_eligible(profile, pid)
            dep = _requires_one_of(pid)
            dep_ok = (not dep) or bool(set(cur) & set(dep))
            if not good or not dep_ok:
                cur.remove(pid)
                removed.append(why if not good else f"{pid}: dependency not met")
                changed = True
                break
    return cur, removed


def blockers(profile: Profile, pid: str, bundle: list[str] | None = None) -> list[dict]:
    """Structured reasons a product cannot be sold to this profile (empty list =
    sellable). Used to explain refusals in plain language. `bundle` is the
    context for dependency checks (None = ignore dependencies)."""
    p = get_store().product(pid)
    if p is None:
        return [{"code": "unknown"}]
    out = []
    if profile.city_tier not in _tiers(p):
        out.append({"code": "city_tier", "have": profile.city_tier,
                    "need": sorted(_tiers(p))})
    me = _int(p.get("min_employees"), 0)
    if profile.employee_count < me:
        out.append({"code": "employees", "have": profile.employee_count, "need": me})
    ms = _int(p.get("min_sites"), 0)
    if profile.num_sites < ms:
        out.append({"code": "sites", "have": profile.num_sites, "need": ms})
    if str(p.get("requires_gstin")).strip().upper() == "Y" and not profile.has_active_gstin:
        out.append({"code": "gstin"})
    dep = _requires_one_of(pid)
    if bundle is not None and dep and not (set(bundle) & set(dep)):
        out.append({"code": "dependency", "need": dep})
    return out
