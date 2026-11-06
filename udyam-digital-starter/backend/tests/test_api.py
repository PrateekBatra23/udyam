import pytest
from fastapi.testclient import TestClient

from tests.conftest import needs_db
import app as appmod

client = TestClient(appmod.app)      # no `with`: startup (DB init) is not triggered


def a_gstin(store, status="Active"):
    return next(g for g, r in store.gstin.items() if r["status"] == status and store.udyam_for_gstin(r))


def test_health_and_catalogue():
    h = client.get("/health").json()
    assert h["products"] == 25 and h["gstin"] == 3534 and h["udyam"] == 2723 and h["today"] == "2026-07-15"
    assert len(client.get("/catalogue").json()) == 25


def test_onboard_autofills_at_least_five_fields(store):
    r = client.post("/onboard", json={"gstin": a_gstin(store)}).json()
    assert r["accepted"] and r["autofilled_fields"] >= 5
    assert r["inferred_segment"]["segment"] in ("micro", "prof", "multi", "mfg")
    assert r["city_tier"] in (1, 2) and r["employee_prior"] >= 1


@pytest.mark.parametrize("status", ["Cancelled", "Suspended"])
def test_onboard_rejects_non_active_with_reason(store, status):
    r = client.post("/onboard", json={"gstin": a_gstin(store, status)}).json()
    assert r["accepted"] is False and status in r["reject_reason"]


def test_onboard_invalid_checksum_and_unknown(store):
    g = a_gstin(store)
    assert client.post("/onboard", json={"gstin": g[:-1] + "A" if g[-1] != "A" else g[:-1] + "B"}).status_code == 422
    assert client.post("/onboard", json={"gstin": "27ABCXD1234E1Z5"}).status_code in (404, 422)


def test_recommend_ignores_client_gstin_flag(store):
    """A client claiming has_active_gstin must not unlock GSTIN-gated products."""
    r = client.post("/advisor/recommend", json={
        "profile": {"segment": "prof", "city_tier": 1, "employee_count": 50, "num_sites": 5,
                    "has_active_gstin": True}, "requested": ["P12"]}).json()
    assert r["refusals"] and r["refusals"][0]["product_id"] == "P12"
    ok = client.post("/advisor/recommend", json={
        "gstin": a_gstin(store), "profile": {"segment": "prof", "city_tier": 1, "employee_count": 50,
                                             "num_sites": 5}, "requested": ["P12"]}).json()
    assert not ok["refusals"]


def test_cancelled_gstin_does_not_unlock_gated_products(store):
    r = client.post("/advisor/recommend", json={
        "gstin": a_gstin(store, "Cancelled"),
        "profile": {"segment": "prof", "city_tier": 1, "employee_count": 50, "num_sites": 5},
        "requested": ["P15"]}).json()
    assert r["refusals"]


def test_quote_endpoint_reconciles_and_checks_eligibility():
    body = {"segment": "multi", "num_sites": 4, "bundle": ["P02", "P10"], "current_spend": 20000,
            "profile": {"segment": "multi", "city_tier": 1, "employee_count": 30, "num_sites": 4,
                        "has_active_gstin": True}}
    q = client.post("/quote", json=body).json()
    assert q["monthly_inr"] == sum(l["monthly_inr"] for l in q["lines"])
    assert q["eligibility"]["ok"]
    bad = client.post("/quote", json={**body, "bundle": ["P10"]}).json()
    assert not bad["eligibility"]["ok"]


def test_demo_profiles_use_real_registry_ids(store):
    ps = client.get("/demo/profiles").json()
    assert len(ps) == 5
    for p in ps[1:4]:
        assert p["gstin"] in store.gstin and store.gstin[p["gstin"]]["status"] == "Active"
        assert p["udyam_number"] in store.udyam


def test_score_returns_band_and_drivers():
    hi = client.post("/score", json={"lead": {"has_gstin": "Y", "segment": "Small manufacturers",
                                              "lead_source": "Referral", "city_tier": 1}}).json()
    lo = client.post("/score", json={"lead": {"has_gstin": "N", "segment": "Micro retail & services",
                                              "lead_source": "WhatsApp campaign", "city_tier": 2}}).json()
    assert hi["probability"] > lo["probability"]
    assert hi["band"] in ("High", "Med") and lo["band"] == "Low" and hi["drivers"]


def test_analytics_numbers_match_the_csv_not_hardcoded(store):
    s = client.get("/analytics/summary").json()
    m = s["metrics"]
    assert s["total_leads"] == 5000 and s["activated"] == 368
    assert m["activation_rate_pct"] == 7.4 and m["median_days_to_activation"] == 17.0
    assert m["churn_6m_pct"] == 15.2 and m["mean_nps"] == 6.9
    assert 15000 <= m["blended_cac_inr"] <= 15100
    assert s["funnel"][-1]["leads"] == 368
    assert s["by_gstin"]["Y"]["rate_pct"] == 9.6 and s["by_gstin"]["N"]["rate_pct"] == 2.0


def test_retention_is_segment_and_contract_level_only_and_flags_low_n():
    r = client.get("/analytics/retention").json()
    assert {x["key"] for x in r["by_segment"]} == {"Micro retail & services", "Professional offices",
                                                   "Small manufacturers", "Small multi-site businesses"}
    six = next(x for x in r["by_contract_months"] if x["key"].startswith("6 "))
    assert six["low_n"] is True
    assert "per bundle" in r["caveat"]


def test_scored_leads_sorted_with_routing_actions():
    r = client.get("/analytics/leads", params={"limit": 20}).json()
    ps = [x["probability"] for x in r["leads"]]
    assert ps == sorted(ps, reverse=True) and r["leads"][0]["action"]
    assert {b["band"] for b in r["bands"]} == {"High", "Med", "Low"}


def test_kyc_endpoints_unreachable_without_consent():
    assert client.get("/kyc/validate", params={"applicant": "K02"}).status_code == 403
    assert client.get("/kyc/validate_all").status_code == 403
    assert client.post("/kyc/upload").status_code == 403


# ------------------------------------------------------------- need Postgres
@needs_db
def test_consent_receipt_roundtrip_and_masking():
    r = client.post("/privacy/consent", json={"business_ref": "27ABCXD1234E1Z5"}).json()
    assert r["business_ref"][-4:] == "E1Z5"
    assert "27ABC" not in r["business_ref"] and r["notice"]["retention_days"] == 180
    got = client.get(f"/privacy/consent/{r['receipt_id']}").json()
    assert got["receipt_id"] == r["receipt_id"] and got["retention_until"]


@needs_db
def test_kyc_after_consent_and_order_flow(store):
    consent = client.post("/privacy/consent", json={"business_ref": "TEST"}).json()["receipt_id"]
    h = {"X-Consent-Receipt": consent}
    g = a_gstin(store)
    prof = {"segment": "prof", "city_tier": 1, "employee_count": 12, "num_sites": 1}
    o = client.post("/order", json={"bundle": ["P02", "P08"], "gstin": g, "profile": prof}).json()
    assert o["order_id"].startswith("ORD-") and o["current_stage_index"] == 0
    assert o["monthly_inr"] > 0 and o["expected_activation"] == "2026-07-20"      # P02 installs in 5 days
    got = client.get(f"/order/{o['order_id']}").json()
    assert got["lines"] and got["stage_eta"][-1] == got["expected_activation"]
    assert client.post(f"/order/{o['order_id']}/advance").json()["current_stage_index"] == 1
    assert client.get("/kyc/validate", params={"applicant": "K02"}, headers=h).status_code == 200


@needs_db
def test_order_with_ineligible_bundle_is_rejected_server_side(store):
    r = client.post("/order", json={"bundle": ["P10"], "gstin": a_gstin(store),
                                    "profile": {"segment": "multi", "city_tier": 1,
                                                "employee_count": 30, "num_sites": 4}})
    assert r.status_code == 422


# ----------------------------------------------------------------- Tier 3
def test_identifier_is_not_accepted_in_a_url_for_onboarding(store):
    assert client.get("/onboard", params={"gstin": a_gstin(store)}).status_code == 405


def test_log_masking_filter_masks_gstin_and_udyam_in_text_and_urls(store):
    import privacy
    g = a_gstin(store)
    out = privacy.mask_text(f'GET /kyc/validate?typed_gstin={g} "UDYAM-MH-00-1234567"')
    assert g not in out and g[-4:] in out and "1234567" not in out and "4567" in out


def test_log_masking_applies_to_real_log_records(store, caplog):
    import logging
    import privacy
    privacy.install_log_masking()
    g = a_gstin(store)
    seen = []

    class Grab(logging.Handler):
        def emit(self, rec):
            seen.append(rec.getMessage())
    h = Grab()
    h.addFilter(privacy.MaskingFilter())
    lg = logging.getLogger("udyam")
    lg.addHandler(h)
    lg.setLevel(logging.INFO)
    lg.info("lookup for %s", g)
    lg.removeHandler(h)
    assert seen and g not in seen[0] and g[-4:] in seen[0]


@needs_db
def test_withdrawn_consent_blocks_kyc_and_erases_the_linked_record(store):
    import tracker.orders as orders
    rid = client.post("/privacy/consent", json={"business_ref": "TEST"}).json()["receipt_id"]
    h = {"X-Consent-Receipt": rid}
    assert client.get("/kyc/validate", params={"applicant": "K02"}, headers=h).status_code == 200
    o = client.post("/order", json={"bundle": ["P01"], "gstin": a_gstin(store),
                                    "profile": {"segment": "prof", "city_tier": 1, "employee_count": 8,
                                                "num_sites": 1}}).json()
    orders.record_kyc(o["order_id"], "APPROVE", "***********ABCD", rid)
    assert client.get(f"/order/{o['order_id']}").json()["kyc_status"] == "APPROVE"
    w = client.post(f"/privacy/consent/{rid}/withdraw").json()
    assert w["kyc_records_erased"] == 1
    got = client.get(f"/order/{o['order_id']}").json()
    assert got["kyc_status"] is None and got["kyc_gstin_masked"] is None
    assert client.get("/kyc/validate", params={"applicant": "K02"}, headers=h).status_code == 403
    assert client.post("/privacy/consent/CNS-DOESNOTEXIST/withdraw").status_code == 404


@needs_db
def test_retention_purge_removes_expired_records_only():
    import datetime
    import db
    import privacy
    import config
    from tracker import orders
    old = orders.create_order(["P01"], None, "***OLD1", order_date=config.TODAY - datetime.timedelta(days=400))
    new = orders.create_order(["P01"], None, "***NEW1")
    orders.record_kyc(old["order_id"], "APPROVE", "***********OLD1")
    orders.record_kyc(new["order_id"], "APPROVE", "***********NEW1")
    privacy.purge_expired()
    assert orders.get_order(old["order_id"])["kyc_status"] is None
    assert orders.get_order(new["order_id"])["kyc_status"] == "APPROVE"
