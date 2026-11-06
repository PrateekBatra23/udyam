"""Rules-only advisor (section 14A): used when no LLM key is present, and as the
candidate generator the LLM is constrained to. Produces Value + Lite bundles,
filtered through the eligibility engine so nothing ineligible is ever returned.
"""
from rules.eligibility import Profile, strip_ineligible, eligible_products
from rules.bundles import VALUE_BUNDLE, LITE_BUNDLE, DEFAULT_QTY
from rules.quote import build_quote


def _reason_for(pid, store):
    p = store.product(pid)
    return f"{p['product_name']} — {p['description']}" if p else pid


def recommend(profile: Profile, current_spend: int | None = None) -> dict:
    from data_store import get_store
    store = get_store()
    seg = profile.segment if profile.segment in VALUE_BUNDLE else "micro"

    value_raw = VALUE_BUNDLE[seg]
    lite_raw = LITE_BUNDLE[seg]
    value, v_removed = strip_ineligible(profile, value_raw)
    lite, l_removed = strip_ineligible(profile, lite_raw)

    def pack(name, bundle, removed):
        q = build_quote(seg, profile.num_sites, bundle, DEFAULT_QTY, current_spend)
        q["bundle"] = name
        q["products"] = [
            {"product_id": pid, "qty": DEFAULT_QTY.get(pid, 1),
             "reason": _reason_for(pid, store)}
            for pid in bundle
        ]
        q["removed_as_ineligible"] = removed
        return q

    return {
        "segment": seg,
        "value": pack("Value", value, v_removed),
        "lite": pack("Lite", lite, l_removed),
        "eligible_product_ids": eligible_products(profile),
        "source": "rules",
    }
