import pytest
from rules import identifiers
from rules.eligibility import Profile, eligible_products, validate_bundle, strip_ineligible, product_eligible
from rules.quote import build_quote


def P(**kw):
    base = dict(segment="micro", city_tier=1, employee_count=10, num_sites=1, has_active_gstin=True)
    base.update(kw)
    return Profile(**base)


# ---------------------------------------------------------------- identifiers
def test_every_registry_gstin_passes_format_and_checksum(store):
    bad = [g for g in store.gstin if not (identifiers.gstin_format_ok(g) and identifiers.gstin_checksum_ok(g))]
    assert not bad


def test_gstin_accepts_X_fourth_pan_char(store):
    g = next(iter(store.gstin))
    assert g[5] == "X" and identifiers.gstin_format_ok(g)


def test_bad_checksum_and_length_rejected(store):
    g = next(iter(store.gstin))
    flipped = g[:-1] + ("A" if g[-1] != "A" else "B")
    assert not identifiers.gstin_checksum_ok(flipped)
    assert not identifiers.gstin_format_ok(g[:-1])


def test_udyam_format_accepts_district_00(store):
    assert all(identifiers.udyam_format_ok(u) for u in store.udyam)
    assert not identifiers.udyam_format_ok("UDYAM-XX-00-123")


def test_ocr_confusion_repair_prefers_registry_entry(store):
    for g in list(store.gstin)[:300]:
        noisy = g.replace("0", "O", 1) if "0" in g else g.replace("1", "I", 1)
        fixed, _ = identifiers.correct_gstin_ocr(noisy, set(store.gstin))
        assert fixed == g, (g, noisy, fixed)


# ---------------------------------------------------------------- eligibility
def test_sdwan_needs_size_sites_gstin_and_base_line():
    assert not product_eligible(P(employee_count=2, num_sites=1), "P10")[0]
    assert not product_eligible(P(employee_count=30, num_sites=2), "P10")[0]          # sites
    assert not product_eligible(P(employee_count=30, num_sites=4, has_active_gstin=False), "P10")[0]
    assert product_eligible(P(employee_count=30, num_sites=4), "P10")[0]
    assert not validate_bundle(P(employee_count=30, num_sites=4), ["P10"])[0]         # dependency
    assert validate_bundle(P(employee_count=30, num_sites=4), ["P02", "P10"])[0]


def test_city_tier_gate_p03_tier1_only():
    assert product_eligible(P(city_tier=1, employee_count=10), "P03")[0]
    assert not product_eligible(P(city_tier=2, employee_count=10), "P03")[0]


@pytest.mark.parametrize("pid,need", [("P03", 5), ("P05", 10), ("P06", 25), ("P12", 3), ("P21", 10), ("P24", 10)])
def test_employee_gates(pid, need):
    assert product_eligible(P(employee_count=need), pid)[0]
    assert not product_eligible(P(employee_count=need - 1), pid)[0]


def test_dependencies_match_spec():
    prof = P(employee_count=50, num_sites=5)
    assert not validate_bundle(prof, ["P09"])[0]
    assert validate_bundle(prof, ["P01", "P09"])[0]
    assert validate_bundle(prof, ["P01", "P12"])[0]
    assert not validate_bundle(prof, ["P12"])[0]
    assert not validate_bundle(P(), ["P23"])[0]
    assert validate_bundle(P(), ["P04", "P23"])[0]
    assert not validate_bundle(P(), ["P07", "P11"])[0]            # postpaid is not an internet line


def test_gstin_gated_products_blocked_without_gstin():
    gated = {"P03", "P05", "P06", "P10", "P12", "P13", "P14", "P15", "P21", "P24"}
    ok = set(eligible_products(P(has_active_gstin=False, employee_count=200, num_sites=10)))
    assert not (gated & ok)


def test_strip_ineligible_cascades_dependents():
    clean, removed = strip_ineligible(P(employee_count=2, has_active_gstin=False), ["P05", "P11", "P07"])
    assert clean == ["P07"] and len(removed) >= 2


# ---------------------------------------------------------------------- quote
def test_micro_priced_at_floor_and_others_at_rounded_midpoint():
    q = build_quote("micro", 1, ["P01"])
    assert q["lines"][0]["unit_price_inr"] == 999
    q = build_quote("prof", 1, ["P01"])
    assert q["lines"][0]["unit_price_inr"] == 1100                    # (999+1199)/2=1099 -> 1100


def test_per_site_multiplies_and_per_line_does_not():
    q = build_quote("prof", 3, ["P02", "P08"])
    p02, p08 = q["lines"]
    assert p02["per_site"] and p02["monthly_inr"] == p02["unit_price_inr"] * 3
    assert not p08["per_site"] and p08["monthly_inr"] == p08["unit_price_inr"]


def test_floor_mode_overrides_segment_midpoint():
    assert build_quote("mfg", 1, ["P05"], price_mode="floor")["lines"][0]["unit_price_inr"] == 8000


def test_totals_reconcile_with_lines_and_savings():
    q = build_quote("multi", 4, ["P02", "P09", "P23"], current_spend=10000)
    assert q["monthly_inr"] == sum(l["monthly_inr"] for l in q["lines"])
    assert q["one_time_inr"] == sum(l["one_time_inr"] for l in q["lines"])
    assert q["contract_months"] == max(l["min_contract_months"] for l in q["lines"])
    s = q["savings"]
    assert s["monthly_saving_inr"] == 10000 - q["monthly_inr"]
    if s["monthly_saving_inr"] > 0:
        assert s["payback_months"] == round(q["one_time_inr"] / s["monthly_saving_inr"], 1)
    assert build_quote("micro", 1, ["P01"])["savings"] is None


# ------------------------------------------------------------------- .env loading
def test_dotenv_parser_handles_comments_quotes_and_blanks():
    import config
    env = config.parse_dotenv(
        '# comment\nLLM_API_KEY=abc123   # a Gemini key\nLLM_MODEL="gemini-2.5-flash"\n'
        "EMPTY=\nDATABASE_URL=postgresql://u:p@h:5432/db\n\nbad line\n")
    assert env == {"LLM_API_KEY": "abc123", "LLM_MODEL": "gemini-2.5-flash", "EMPTY": "",
                   "DATABASE_URL": "postgresql://u:p@h:5432/db"}


def test_unknown_product_ids_are_stripped_not_crashed_on():
    clean, removed = strip_ineligible(P(), ["P01", "P99", "NOPE"])
    assert clean == ["P01"] and len(removed) == 2
    ok, reasons = validate_bundle(P(), ["P99"])
    assert not ok and "unknown product" in reasons[0]
