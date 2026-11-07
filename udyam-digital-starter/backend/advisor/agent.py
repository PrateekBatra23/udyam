"""Advisor entry point (spec O2).

Design: candidate-set constraining + server-side backstop.
  1. The rules answer (fallback.recommend) is ALWAYS computed first. It is the
     no-LLM response and the constrained candidate set.
  2. With LLM_API_KEY set, Gemini is asked to tailor it. Default = ONE call: the first
     message already carries the eligible catalogue with prices, the starting Value and
     Lite bundles, the owner's priority and spend, so no tool round trips are needed
     (~5-10 s instead of ~20-35 s). LLM_USE_TOOLS=1 switches to the multi-round
     tool-calling loop (advisor/llm.py run_chat) for the same inputs.
  3. Whatever the model returns is re-validated by strip_ineligible, and a bundle that
     loses its internet line falls back to the rules bundle. Prices always come from the
     server's quote engine, never from the model. The model can therefore never put an
     invalid bundle or a made-up price in front of the owner.
Refusals (ineligible requests) always come from the rules engine.
"""
import json
import re

import config
from data_store import get_store
from rules.eligibility import Profile, strip_ineligible
from rules.bundles import CONNECTIVITY
from rules.quote import _price_point
from advisor import fallback, llm, messages
from advisor.tools import TOOL_SCHEMAS, run_tool

LANGUAGE_NAME = {"en": "English", "hi": "Hindi"}

_COMMON_RULES = """You are Accel Business's onboarding advisor for small businesses in India.
You tailor a telecom + cloud bundle for ONE business whose profile is fixed by the server.
Rules you must follow:
- Choose ONLY product_ids that appear in the eligible catalogue. Never invent products.
- Every bundle needs an internet line (P01-P06) before add-ons that depend on one
  (check each product's requires_one_of against the bundle).
- 'value' is the recommended bundle. Start from starting_point.value and KEEP every product in it
  (the core internet, mobile, email and security items are what make it a complete bundle). Tailor it to
  the owner's top_priority by ADDING at most 2 eligible products and SWAPPING at most 1 for a better
  fit. Only remove a product if it directly conflicts with the priority, and keep any product the owner
  explicitly asked for (added_because = requested). 'lite' is the cheaper bundle: connectivity plus ONE
  core item, starting from starting_point.lite - change it only if the priority clearly calls for it.
- How to read top_priority: price -> keep Value lean and lean on Lite; reliability -> backup link
  (failover) / static IP; customers -> WhatsApp, SMS, toll-free, telephony; security -> endpoint
  security, firewall, secure Wi-Fi; safety -> CCTV.
- The server already explained any request it had to refuse (see refused_requests): do not add those
  products and do not mention them.
- 'rationale': plain language, in the owner's preferred_language, at most 80 words, no product codes.
  Say why THIS bundle fits THIS business and its top_priority. Do not state any prices, totals or savings -
  the app shows the numbers."""

SYSTEM_SINGLE = _COMMON_RULES + """
- You have everything you need in the first message and no tools: answer immediately.
Return ONLY JSON: {"value":["P01",...],"lite":["P04",...],"rationale":"..."}"""

SYSTEM_TOOLS = _COMMON_RULES + """
- Call get_catalogue first. Verify each bundle with check_eligibility; be economical (at most one call
  per bundle, several may be requested at once), then answer.
Return ONLY JSON: {"value":["P01",...],"lite":["P04",...],"rationale":"..."}"""

SYSTEM = SYSTEM_TOOLS      # backwards-compatible name


def _extract_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def build_brief(profile: Profile, base: dict, current_spend, language, priority) -> dict:
    """Everything the model needs, in one message: the ELIGIBLE catalogue with the prices this
    business would pay, the starting bundles, and the owner's priority. Prices are the server's."""
    store = get_store()
    sites = max(profile.num_sites, 1)
    catalogue = []
    for pid in base["eligible_product_ids"]:
        p = store.product(pid)
        per_site = str(p.get("unit", "")).strip().lower() == "per site"
        mult = sites if per_site else 1
        catalogue.append({
            "product_id": pid, "name": p["product_name"], "category": p["category"],
            "description": p["description"], "unit": p["unit"],
            "requires_one_of": [x for x in str(p.get("requires_one_of") or "").split("|")
                                if x and x != "nan"],
            "min_contract_months": int(p["min_contract_months"]),
            "monthly_inr_value_pricing": _price_point(p, profile.segment, "auto") * mult,
            "monthly_inr_lite_pricing": _price_point(p, profile.segment, "floor") * mult,
        })

    def bundle(key):
        q = base[key]
        return {"product_ids": [p["product_id"] for p in q["products"]],
                "monthly_inr": q["monthly_inr"], "one_time_inr": q["one_time_inr"],
                "contract_months": q["contract_months"],
                "added_because": {p["product_id"]: p["added_because"]
                                  for p in q["products"] if p.get("added_because")}}

    ret = base.get("retention") or {}
    return {
        "business": {"segment": profile.segment, "city_tier": profile.city_tier,
                     "employee_count": profile.employee_count, "num_sites": sites,
                     "has_active_gstin": profile.has_active_gstin},
        "owner": {"top_priority": priority,
                  "top_priority_meaning": messages.PRIORITY_LABEL["en"].get(priority),
                  "current_monthly_spend_inr": current_spend,
                  "preferred_language": LANGUAGE_NAME.get(language, language)},
        "eligible_catalogue": catalogue,
        "starting_point": {"value": bundle("value"), "lite": bundle("lite")},
        "refused_requests": [r["name"] for r in base.get("refusals", [])],
        "segment_6m_churn_pct": ret.get("segment_6m_churn_pct"),
    }


def _llm_refine(profile: Profile, base: dict, current_spend, language, priority, client=None,
                use_tools: bool | None = None) -> dict:
    if client is None:
        client = llm.make_client()
    use_tools = config.LLM_USE_TOOLS if use_tools is None else use_tools
    brief = build_brief(profile, base, current_spend, language, priority)
    if use_tools:
        text = llm.run_chat(client, SYSTEM_TOOLS, brief, TOOL_SCHEMAS,
                            lambda name, args: run_tool(name, args, profile, current_spend))
    else:
        text = llm.generate_json(client, SYSTEM_SINGLE, brief)
    return _extract_json(text)


def _accept(profile: Profile, proposed: list, fallback_bundle: list) -> list:
    """Re-validate the model's bundle; fall back if it lost the internet line."""
    clean, _ = strip_ineligible(profile, [str(p) for p in proposed])
    if not clean or not any(p in CONNECTIVITY for p in clean):
        return fallback_bundle
    return clean


def recommend(profile_dict: dict, current_spend: int | None = None, language: str = "en",
              priority: str | None = None, requested: list | None = None,
              message: str | None = None, client=None, use_tools: bool | None = None) -> dict:
    profile = Profile.from_dict(profile_dict)
    base = fallback.recommend(profile, current_spend, language, priority, requested, message)
    if not (config.USE_LLM or client is not None):
        return base                                    # rules-only: no key, no LLM

    try:
        parsed = _llm_refine(profile, base, current_spend, language, base["priority"], client, use_tools)
        lang = fallback._lang(language)
        seg = base["segment"]
        v_ids = _accept(profile, parsed.get("value", []), [p["product_id"] for p in base["value"]["products"]])
        l_ids = _accept(profile, parsed.get("lite", []), [p["product_id"] for p in base["lite"]["products"]])
        added_by = {p["product_id"]: p["added_because"] for p in base["value"]["products"]
                    if p.get("added_because")}
        base["value"] = fallback._pack("Value", v_ids, base["value"]["removed_as_ineligible"], profile,
                                       seg, current_spend, "auto", lang, added_by)
        base["lite"] = fallback._pack("Lite", l_ids, base["lite"]["removed_as_ineligible"], profile,
                                      seg, current_spend, "floor", lang, {})
        text = (parsed.get("rationale") or "").strip()
        if text:
            refusal_text = " ".join(r["message"] for r in base["refusals"])
            base["rationale"] = (refusal_text + " " + text).strip()
        base["source"] = "llm"
    except Exception as e:      # any LLM failure -> the rules answer stands
        base["source"] = "rules"
        base["llm_error"] = f"{type(e).__name__}: {e}"
    return base
