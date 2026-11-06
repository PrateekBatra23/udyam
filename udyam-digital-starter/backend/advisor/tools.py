"""Tools the LLM advisor may call (spec O2). Thin wrappers over the rules engine
so the model never computes eligibility or price itself.

The business PROFILE is bound server-side (the model cannot edit it) and the
catalogue it can see is already restricted to products eligible for that
profile - candidate-set constraining.
"""
from rules.eligibility import Profile, eligible_products, validate_bundle
from rules.quote import build_quote
from rules.bundles import DEFAULT_QTY
from data_store import get_store


def tool_get_catalogue(profile: Profile) -> list[dict]:
    """Only products eligible for this profile (dependencies are checked later,
    on the bundle)."""
    store = get_store()
    return [{
        "product_id": pid,
        "name": store.product(pid)["product_name"],
        "category": store.product(pid)["category"],
        "description": store.product(pid)["description"],
        "requires_one_of": str(store.product(pid).get("requires_one_of") or "").replace("nan", ""),
        "min_contract_months": int(store.product(pid)["min_contract_months"]),
    } for pid in eligible_products(profile)]


def tool_check_eligibility(profile: Profile, bundle: list[str]) -> dict:
    ok, reasons = validate_bundle(profile, [str(b) for b in bundle])
    return {"ok": ok, "reasons": reasons}


def tool_build_quote(profile: Profile, bundle: list[str], current_spend=None,
                     price_mode: str = "auto") -> dict:
    q = build_quote(profile.segment, profile.num_sites, [str(b) for b in bundle],
                    DEFAULT_QTY, current_spend, price_mode)
    return {k: q[k] for k in ("monthly_inr", "one_time_inr", "contract_months", "savings")} | {
        "lines": [{"product_id": l["product_id"], "monthly_inr": l["monthly_inr"]} for l in q["lines"]]}


def tool_gstin_lookup(gstin: str) -> dict:
    r = get_store().gstin_lookup(str(gstin).upper())
    if not r:
        return {"found": False}
    return {"found": True, "status": r["status"], "constitution": r["constitution"],
            "state": r["state"]}


def tool_udyam_lookup(udyam: str) -> dict:
    r = get_store().udyam_lookup(str(udyam).upper())
    if not r:
        return {"found": False}
    return {"found": True, "enterprise_type": r["enterprise_type"],
            "major_activity": r["major_activity"], "nic_description": r["nic_description"]}


def run_tool(name: str, args: dict, profile: Profile, current_spend=None):
    """Dispatch with the profile bound by the server. Unknown tool -> error dict."""
    args = args or {}
    if name == "get_catalogue":
        return tool_get_catalogue(profile)
    if name == "check_eligibility":
        return tool_check_eligibility(profile, args.get("bundle", []))
    if name == "build_quote":
        return tool_build_quote(profile, args.get("bundle", []), current_spend,
                                args.get("price_mode", "auto"))
    if name == "gstin_lookup":
        return tool_gstin_lookup(args.get("gstin", ""))
    if name == "udyam_lookup":
        return tool_udyam_lookup(args.get("udyam", ""))
    return {"error": f"unknown tool {name}"}


# JSON schema the LLM sees (Anthropic tool-use format)
_BUNDLE = {"type": "array", "items": {"type": "string"}}
TOOL_SCHEMAS = [
    {"name": "get_catalogue",
     "description": "List the products that are eligible for THIS business. Call this first.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "check_eligibility",
     "description": "Validate a candidate bundle (product ids) against every eligibility and dependency rule.",
     "input_schema": {"type": "object", "properties": {"bundle": _BUNDLE}, "required": ["bundle"]}},
    {"name": "build_quote",
     "description": "Price a candidate bundle for this business (monthly, one-time, contract, savings).",
     "input_schema": {"type": "object", "properties": {
         "bundle": _BUNDLE, "price_mode": {"type": "string", "enum": ["auto", "floor"]}},
         "required": ["bundle"]}},
    {"name": "gstin_lookup", "description": "Look up a GSTIN's status in the registry.",
     "input_schema": {"type": "object", "properties": {"gstin": {"type": "string"}}, "required": ["gstin"]}},
    {"name": "udyam_lookup", "description": "Look up a Udyam registration.",
     "input_schema": {"type": "object", "properties": {"udyam": {"type": "string"}}, "required": ["udyam"]}},
]
