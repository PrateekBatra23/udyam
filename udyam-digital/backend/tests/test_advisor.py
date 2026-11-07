import random
from types import SimpleNamespace

import config
import demo
from advisor import agent, fallback
from rules.eligibility import Profile, validate_bundle, eligible_products


def rec(profile, **kw):
    return agent.recommend(profile, **kw)


def prof_of(p, gstin_active):
    d = dict(p)
    d["has_active_gstin"] = gstin_active
    return d


def ids(q):
    return [p["product_id"] for p in q["products"]]


def test_micro_no_gstin_gets_lite_leaning_and_no_gated_products(store):
    p = demo.profiles()[0]
    r = rec(prof_of(p["profile"], False), current_spend=p["current_spend"], priority=p["priority"])
    assert r["recommended"] == "lite"
    gated = {pid for pid, row in store.products.items() if row["requires_gstin"] == "Y"}
    assert not (gated & set(ids(r["value"]))) and not (gated & set(ids(r["lite"])))
    assert r["lite"]["monthly_inr"] <= r["value"]["monthly_inr"]


def test_pinned_profiles_2_3_4_pass_all_rules_and_have_expected_shape():
    ps = {p["id"]: p for p in demo.profiles()}
    r2 = rec(prof_of(ps[2]["profile"], True), current_spend=ps[2]["current_spend"])
    assert "P12" in ids(r2["value"])
    r3 = rec(prof_of(ps[3]["profile"], True), priority="reliability")
    assert {"P10", "P09", "P23"} <= set(ids(r3["value"]))
    r4 = rec(prof_of(ps[4]["profile"], True))
    assert {"P05", "P21", "P24"} <= set(ids(r4["value"]))
    for r, p in ((r2, 2), (r3, 3), (r4, 4)):
        prof = Profile.from_dict(prof_of(ps[p]["profile"], True))
        assert validate_bundle(prof, ids(r["value"]))[0]
        assert validate_bundle(prof, ids(r["lite"]))[0]


def test_probe_refuses_sdwan_for_two_person_shop_and_explains():
    p = demo.profiles()[4]
    r = rec(prof_of(p["profile"], False), message=p["message"], requested=p["requested"])
    assert "P10" not in ids(r["value"]) and "P10" not in ids(r["lite"])
    ref = r["refusals"][0]
    assert ref["product_id"] == "P10"
    codes = {b["code"] for b in ref["blockers"]}
    # fibre (P01) is already in the micro bundle, so the dependency itself is satisfied
    assert {"employees", "sites", "gstin"} <= codes and "dependency" not in codes
    assert "Managed SD-WAN" in r["rationale"] and "employees" in r["rationale"]


def test_adversarial_leased_line_for_one_person_shop_is_refused():
    r = rec({"segment": "micro", "city_tier": 2, "employee_count": 1, "num_sites": 1,
             "has_active_gstin": False}, message="please add a leased line for my 1-person shop")
    assert r["refusals"] and r["refusals"][0]["product_id"] == "P05"
    assert "P05" not in ids(r["value"]) + ids(r["lite"])


def test_refusal_message_in_hindi():
    r = rec({"segment": "micro", "city_tier": 2, "employee_count": 2, "num_sites": 1,
             "has_active_gstin": False}, requested=["P10"], language="hi")
    assert "नहीं जोड़ सकता" in r["refusals"][0]["message"]
    assert r["language"] == "hi"


def test_requested_eligible_product_is_added():
    r = rec({"segment": "prof", "city_tier": 1, "employee_count": 12, "num_sites": 1,
             "has_active_gstin": True}, message="I also need CCTV")
    assert "P23" in ids(r["value"]) and not r["refusals"]


def test_priority_adds_eligible_addons_only():
    base = {"segment": "multi", "city_tier": 1, "employee_count": 30, "num_sites": 4,
            "has_active_gstin": True}
    r = rec(base, priority="security")
    assert "P20" in ids(r["value"])
    r2 = rec({**base, "has_active_gstin": False}, priority="customers")
    assert not ({"P15", "P14", "P13"} & set(ids(r2["value"])))          # all GSTIN-gated


def test_small_mfg_swaps_leased_line_for_fibre_and_keeps_dependents_valid():
    d = {"segment": "mfg", "city_tier": 2, "employee_count": 4, "num_sites": 1,
         "has_active_gstin": False}
    r = rec(d)
    assert validate_bundle(Profile.from_dict(d), ids(r["value"]))[0]
    assert any(p in ids(r["value"]) for p in ("P01", "P02", "P04"))


def test_random_profiles_never_produce_an_invalid_bundle(store):
    """Acceptance: for random profiles the recommended bundle passes all rules."""
    leads = store.leads.sample(300, random_state=7)
    rng = random.Random(3)
    for l in leads.itertuples():
        active = l.has_gstin == "Y" and store.gstin[l.gstin]["status"] == "Active"
        d = {"segment": config.SEGMENT_CODE[l.segment], "city_tier": int(l.city_tier),
             "employee_count": int(l.employee_count), "num_sites": int(l.num_sites),
             "has_active_gstin": active}
        r = rec(d, current_spend=int(l.monthly_telecom_spend_inr),
                priority=rng.choice(["price", "reliability", "customers", "security", "safety", None]),
                requested=rng.sample(list(store.products), 2))
        prof = Profile.from_dict(d)
        for b in ("value", "lite"):
            ok, why = validate_bundle(prof, ids(r[b]))
            assert ok, (d, b, ids(r[b]), why)
        assert set(ids(r["value"])) <= set(eligible_products(prof))


def test_questions_are_at_most_three_and_shrink_when_known():
    p = Profile(segment="prof")
    assert len(fallback.questions(p)) == 3
    known = {"num_sites": 1, "current_spend": None, "priority": None}
    assert [q["id"] for q in fallback.questions(p, known=known)] == ["current_spend", "priority"]


def test_retention_block_uses_segment_level_churn(store):
    r = rec({"segment": "micro", "city_tier": 2, "employee_count": 3, "num_sites": 1,
             "has_active_gstin": False})
    assert r["retention"]["segment_6m_churn_pct"] == round(store.churn_by_segment["micro"]["churn"] * 100, 1)
    assert "left within 6 months" in r["rationale"]
    assert r["retention"]["value_ltv_inr"] > 0


def test_hindi_refusal_reads_as_a_sentence():
    r = rec({"segment": "micro", "city_tier": 2, "employee_count": 2, "num_sites": 1,
             "has_active_gstin": False}, requested=["P10"], language="hi")
    m = r["refusals"][0]["message"]
    assert "क्योंकि:" in m and "के लिए कम से कम" not in m
