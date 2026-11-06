"""Advisor entry point (spec O2).

Design: candidate-set constraining + server-side backstop.
  1. The rules answer (fallback.recommend) is ALWAYS computed first. It is the
     no-LLM response and the constrained candidate set.
  2. With LLM_API_KEY set, Gemini runs a tool-calling loop (advisor/llm.py). The business profile
     is bound server-side, get_catalogue only ever returns eligible products, and
     the model's job is to choose/trim within them and explain in the owner's
     language.
  3. Whatever the model returns is re-validated by strip_ineligible, and a
     bundle that loses its internet line falls back to the rules bundle, so the
     model can never put an invalid bundle in front of the owner.
Refusals (ineligible requests) always come from the rules engine.
"""
import json
import re

import config
from rules.eligibility import Profile, strip_ineligible
from rules.bundles import CONNECTIVITY
from advisor import fallback, llm, messages
from advisor.tools import TOOL_SCHEMAS, run_tool

SYSTEM = """You are Accel Business's onboarding advisor for small businesses in India.
You recommend telecom + cloud bundles for ONE business whose profile is fixed by the server.
Rules you must follow:
- Call get_catalogue first; choose ONLY product_ids it returns. Never invent products.
- Verify every bundle with check_eligibility before answering; fix anything it flags.
- Every bundle needs an internet line (P01-P06) before add-ons that depend on one.
- 'value' is the recommended bundle; 'lite' is the cheaper bundle: connectivity plus ONE core item.
- Explain in plain language, in the owner's preferred language. No product codes in the prose.
Return ONLY JSON: {"value":["P01",...],"lite":["P04",...],"rationale":"..."}"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def _llm_refine(profile: Profile, base: dict, current_spend, language, priority, client=None) -> dict:
    if client is None:
        client = llm.make_client()
    brief = {
        "profile": {"segment": profile.segment, "city_tier": profile.city_tier,
                    "employee_count": profile.employee_count, "num_sites": profile.num_sites,
                    "has_active_gstin": profile.has_active_gstin},
        "current_monthly_spend_inr": current_spend,
        "top_priority": priority,
        "preferred_language": language,
        "eligible_product_ids": base["eligible_product_ids"],
        "starting_point": {"value": [p["product_id"] for p in base["value"]["products"]],
                           "lite": [p["product_id"] for p in base["lite"]["products"]]},
    }
    final_text = llm.run_chat(
        client, SYSTEM, brief, TOOL_SCHEMAS,
        lambda name, args: run_tool(name, args, profile, current_spend))
    return _extract_json(final_text)


def _accept(profile: Profile, proposed: list, fallback_bundle: list) -> list:
    """Re-validate the model's bundle; fall back if it lost the internet line."""
    clean, _ = strip_ineligible(profile, [str(p) for p in proposed])
    if not clean or not any(p in CONNECTIVITY for p in clean):
        return fallback_bundle
    return clean


def recommend(profile_dict: dict, current_spend: int | None = None, language: str = "en",
              priority: str | None = None, requested: list | None = None,
              message: str | None = None, client=None) -> dict:
    profile = Profile.from_dict(profile_dict)
    base = fallback.recommend(profile, current_spend, language, priority, requested, message)
    if not (config.USE_LLM or client is not None):
        return base

    try:
        parsed = _llm_refine(profile, base, current_spend, language, priority, client)
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
