"""Tool definitions the LLM advisor may call (section O2). Thin wrappers over the
rules engine so the model never computes eligibility or price itself."""
from rules.eligibility import Profile, eligible_products, validate_bundle
from rules.quote import build_quote
from data_store import get_store


def tool_get_catalogue(eligible_only_for: dict | None = None) -> list[dict]:
    store = get_store()
    ids = (eligible_products(Profile.from_dict(eligible_only_for))
           if eligible_only_for else list(store.products))
    return [{
        "product_id": pid,
        "name": store.product(pid)["product_name"],
        "category": store.product(pid)["category"],
        "description": store.product(pid)["description"],
    } for pid in ids]


def tool_check_eligibility(profile: dict, bundle: list[str]) -> dict:
    ok, reasons = validate_bundle(Profile.from_dict(profile), bundle)
    return {"ok": ok, "reasons": reasons}


def tool_build_quote(profile: dict, bundle: list[str],
                     current_spend: int | None = None) -> dict:
    p = Profile.from_dict(profile)
    return build_quote(p.segment, p.num_sites, bundle, current_spend=current_spend)


def tool_gstin_lookup(gstin: str) -> dict | None:
    return get_store().gstin_lookup(gstin)


def tool_udyam_lookup(udyam: str) -> dict | None:
    return get_store().udyam_lookup(udyam)


# JSON schema the LLM sees (Anthropic tool-use format)
TOOL_SCHEMAS = [
    {"name": "get_catalogue", "description": "List products, optionally only those eligible for a profile.",
     "input_schema": {"type": "object", "properties": {"eligible_only_for": {"type": "object"}}}},
    {"name": "check_eligibility", "description": "Validate a bundle against all rules.",
     "input_schema": {"type": "object", "properties": {"profile": {"type": "object"},
                      "bundle": {"type": "array", "items": {"type": "string"}}},
                      "required": ["profile", "bundle"]}},
    {"name": "build_quote", "description": "Price a bundle for a profile.",
     "input_schema": {"type": "object", "properties": {"profile": {"type": "object"},
                      "bundle": {"type": "array", "items": {"type": "string"}},
                      "current_spend": {"type": "integer"}},
                      "required": ["profile", "bundle"]}},
]

DISPATCH = {
    "get_catalogue": tool_get_catalogue,
    "check_eligibility": tool_check_eligibility,
    "build_quote": tool_build_quote,
    "gstin_lookup": tool_gstin_lookup,
    "udyam_lookup": tool_udyam_lookup,
}
