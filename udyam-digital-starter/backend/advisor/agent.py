"""Advisor entry point (section O2).

Design: candidate-set constraining. We ALWAYS compute the rules-only Value/Lite
recommendation first (fallback.recommend) — that is both the no-LLM answer and
the constrained candidate set. When an LLM key is present, we ask the model only
to (a) choose/trim within the eligible set and (b) write the plain-language
rationale in the owner's language. The server-side result is then re-validated
by strip_ineligible so the model can never introduce an ineligible product.
"""
import json
import config
from rules.eligibility import Profile, strip_ineligible
from advisor import fallback
from advisor.tools import TOOL_SCHEMAS, DISPATCH

SYSTEM = """You are Accel Business's onboarding advisor for small businesses in India.
You recommend telecom + cloud bundles. You MUST only choose products from the
eligible_product_ids given to you. Never invent products or ignore eligibility.
Explain choices in plain language, in the owner's preferred language.
Return STRICT JSON: {"value":[pids],"lite":[pids],"rationale":"..."}"""


def recommend(profile_dict: dict, current_spend: int | None = None,
              language: str = "en") -> dict:
    profile = Profile.from_dict(profile_dict)
    base = fallback.recommend(profile, current_spend)   # rules answer + candidate set

    if not config.USE_LLM:
        base["language"] = language
        return base

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.LLM_API_KEY)
        prompt = {
            "profile": profile_dict,
            "eligible_product_ids": base["eligible_product_ids"],
            "suggested_value": [p["product_id"] for p in base["value"]["products"]],
            "suggested_lite": [p["product_id"] for p in base["lite"]["products"]],
            "preferred_language": language,
        }
        msg = client.messages.create(
            model=config.LLM_MODEL, max_tokens=1024,
            system=SYSTEM,
            tools=TOOL_SCHEMAS,
            messages=[{"role": "user", "content": json.dumps(prompt)}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        parsed = json.loads(text)
        # server-side backstop: re-validate whatever the model returned
        value, _ = strip_ineligible(profile, parsed.get("value", []))
        lite, _ = strip_ineligible(profile, parsed.get("lite", []))
        from rules.quote import build_quote
        from rules.bundles import DEFAULT_QTY
        base["value"].update(build_quote(profile.segment, profile.num_sites, value,
                                         DEFAULT_QTY, current_spend))
        base["lite"].update(build_quote(profile.segment, profile.num_sites, lite,
                                        DEFAULT_QTY, current_spend))
        base["rationale"] = parsed.get("rationale", "")
        base["source"] = "llm"
    except Exception as e:  # any LLM failure -> graceful fall back to rules
        base["source"] = "rules"
        base["llm_error"] = str(e)
    base["language"] = language
    return base
