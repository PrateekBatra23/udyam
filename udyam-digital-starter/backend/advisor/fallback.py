"""Rules-only advisor (spec 14A). It is both the no-LLM answer AND the candidate
generator the LLM path is constrained to, so it must be correct on its own.

Everything returned has passed the eligibility engine: nothing ineligible can
leave this module.
"""
from rules.eligibility import (Profile, strip_ineligible, eligible_products,
                               validate_bundle, product_eligible, blockers)
from rules.bundles import (VALUE_BUNDLE, LITE_BUNDLE, DEFAULT_QTY, CONNECTIVITY,
                           CONNECTIVITY_PREF, PRIORITY_ADDONS, PRIORITIES,
                           ALTERNATIVES, REQUEST_KEYWORDS)
from rules.quote import build_quote
from advisor import messages
from data_store import get_store

MAX_PRIORITY_ADDONS = 2


def _lang(lang: str) -> str:
    return lang if lang in messages.WHY else "en"


def _name(pid: str) -> str:
    p = get_store().product(pid)
    return p["product_name"] if p else pid


def _can_add(profile: Profile, bundle: list[str], pid: str) -> bool:
    ok, _ = validate_bundle(profile, bundle + [pid])
    return ok


def assemble(profile: Profile, raw: list[str], seg: str) -> tuple[list[str], list[str]]:
    """Filter a segment bundle through the rules, then repair it: if the base
    internet line was removed, swap in the first eligible alternative and re-add
    dependents that become valid. Returns (bundle, removed_reasons)."""
    bundle, removed = strip_ineligible(profile, raw)
    if not any(p in CONNECTIVITY for p in bundle):
        for alt in CONNECTIVITY_PREF.get(seg, CONNECTIVITY_PREF["micro"]):
            if product_eligible(profile, alt)[0]:
                bundle = [alt] + bundle
                break
        for pid in raw:                     # dependents that are valid again
            if pid not in bundle and _can_add(profile, bundle, pid):
                bundle.append(pid)
    # keep the segment's own ordering, connectivity first
    bundle.sort(key=lambda p: (p not in CONNECTIVITY, raw.index(p) if p in raw else 99))
    return bundle, removed


def parse_requests(requested: list[str] | None, message: str | None) -> list[str]:
    """Product ids the owner asked for, from explicit ids and/or free text."""
    store = get_store()
    out = [r.upper() for r in (requested or []) if r and r.upper() in store.products]
    text = (message or "").lower()
    for phrase, pid in sorted(REQUEST_KEYWORDS, key=lambda kv: -len(kv[0])):
        if phrase in text and pid not in out:
            # 'pos' / 'sms' / 'sip' / 'iot' / '1g' are short: require a word boundary
            import re
            if re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text):
                out.append(pid)
                text = text.replace(phrase, " ")   # do not let 'leased line' also hit 'line 100'
    return out


def explain_refusal(profile: Profile, pid: str, context: list[str], lang: str) -> dict:
    lang = _lang(lang)
    bl = blockers(profile, pid, context)
    reasons = [messages.blocker_text(lang, b, _name) for b in bl]
    alts = []
    for a in ALTERNATIVES.get(pid, []):
        if not blockers(profile, a, context + [a]) or not blockers(profile, a, None):
            alts.append(a)
    alt_names = [_name(a) for a in alts[:2]]
    return {"product_id": pid, "name": _name(pid), "blockers": bl, "reasons": reasons,
            "alternatives": [{"product_id": a, "name": _name(a)} for a in alts[:2]],
            "message": messages.refusal(lang, _name(pid), reasons, alt_names)}


def _pack(name: str, bundle: list[str], removed: list[str], profile: Profile, seg: str,
          current_spend, price_mode: str, lang: str, added_by: dict) -> dict:
    store = get_store()
    q = build_quote(seg, profile.num_sites, bundle, DEFAULT_QTY, current_spend, price_mode)
    q["bundle"] = name
    q["products"] = []
    for l in q["lines"]:
        pid = l["product_id"]
        p = store.product(pid)
        dep = [x for x in str(p.get("requires_one_of") or "").split("|") if x and x != "nan"]
        l["requires_one_of"] = dep
        q["products"].append({
            "product_id": pid, "name": l["name"], "category": l["category"],
            "qty": l["qty"], "reason": messages.why(lang, pid, p["description"]),
            "requires_one_of": dep, "added_because": added_by.get(pid),
            "monthly_inr": l["monthly_inr"], "one_time_inr": l["one_time_inr"]})
    q["removed_as_ineligible"] = removed
    return q


def questions(profile: Profile, lang: str = "en", known: dict | None = None) -> list[dict]:
    """The 2-3 questions the advisor still has to ask. Everything else came from
    GSTIN autofill + the inferred segment."""
    lang = _lang(lang)
    prior = get_store().sites_prior.get(profile.segment, 1)
    qs = [
        {"id": "num_sites", "type": "number", "min": 1, "max": 50, "default": prior,
         "text": messages.QUESTIONS[lang]["num_sites"]},
        {"id": "current_spend", "type": "number", "min": 0, "step": 100, "default": None,
         "text": messages.QUESTIONS[lang]["current_spend"],
         "why": messages.QUESTION_WHY[lang]},
        {"id": "priority", "type": "choice", "default": "price",
         "text": messages.QUESTIONS[lang]["priority"],
         "options": [{"value": p, "label": messages.PRIORITY_LABEL[lang][p]} for p in PRIORITIES]},
    ]
    if known:
        qs = [q for q in qs if known.get(q["id"]) is None]
    return qs


def recommend(profile: Profile, current_spend: int | None = None, language: str = "en",
              priority: str | None = None, requested: list[str] | None = None,
              message: str | None = None) -> dict:
    store = get_store()
    lang = _lang(language)
    seg = profile.segment if profile.segment in VALUE_BUNDLE else "micro"
    priority = priority if priority in PRIORITIES else None

    value, v_removed = assemble(profile, VALUE_BUNDLE[seg], seg)
    lite, l_removed = assemble(profile, LITE_BUNDLE[seg], seg)

    added_by = {}
    # owner's top priority -> a couple of extra eligible add-ons in Value
    n = 0
    for pid in PRIORITY_ADDONS.get(priority or "", []):
        if n >= MAX_PRIORITY_ADDONS:
            break
        if pid not in value and _can_add(profile, value, pid):
            value.append(pid)
            added_by[pid] = "priority:" + priority
            n += 1

    # explicit requests: add if allowed, otherwise refuse with reasons
    refusals, accepted = [], []
    for pid in parse_requests(requested, message):
        if pid in value:
            accepted.append({"product_id": pid, "name": _name(pid), "already_included": True})
            continue
        bl = blockers(profile, pid, value + [pid])
        if not bl:
            value.append(pid)
            added_by[pid] = "requested"
            accepted.append({"product_id": pid, "name": _name(pid), "already_included": False})
        else:
            refusals.append(explain_refusal(profile, pid, value + [pid], lang))

    # final backstop: nothing ineligible may leave this function
    value, extra_v = strip_ineligible(profile, value)
    lite, extra_l = strip_ineligible(profile, lite)
    v_removed += extra_v
    l_removed += extra_l

    price_first = priority == "price"
    value_q = _pack("Value", value, v_removed, profile, seg, current_spend, "auto", lang, added_by)
    lite_q = _pack("Lite", lite, l_removed, profile, seg, current_spend, "floor", lang, {})

    seg_stats = store.churn_by_segment.get(seg)
    churn = seg_stats["churn"] if seg_stats else 0.0
    retention = {
        "segment_6m_churn_pct": round(churn * 100, 1),
        "segment_mean_nps": seg_stats["nps"] if seg_stats else None,
        "n_activated": seg_stats["n"] if seg_stats else 0,
        "value_ltv_inr": round(value_q["monthly_inr"] * value_q["contract_months"] * (1 - churn)),
        "lite_ltv_inr": round(lite_q["monthly_inr"] * lite_q["contract_months"] * (1 - churn)),
        "basis": "monthly x contract months x (1 - segment 6-month churn). Segment-level only "
                 "(368 activated / 56 churned customers is too few to cut by bundle).",
    }

    rationale = messages.rationale(
        lang, seg, profile.employee_count, profile.num_sites,
        [_name(p) for p in value], priority, retention["segment_6m_churn_pct"])
    if refusals:
        rationale = " ".join(r["message"] for r in refusals) + " " + rationale

    return {
        "segment": seg, "priority": priority,
        "recommended": "lite" if price_first else "value",
        "value": value_q, "lite": lite_q,
        "refusals": refusals, "requested_added": accepted,
        "rationale": rationale, "retention": retention,
        "eligible_product_ids": eligible_products(profile),
        "language": lang if lang == language else "en",
        "source": "rules",
    }
