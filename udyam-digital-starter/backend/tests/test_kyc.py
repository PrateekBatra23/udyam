"""KYC decision logic. Unit tests feed synthetic OCR output (no Tesseract) so the
rules - including the exact 90-day boundary - are tested precisely; the `ocr`
marked tests then run the real pipeline on the specimen documents."""
import glob
import os
from datetime import date, timedelta

import pytest

import config
from kyc import validate, ocr

DOC_TYPES = ["gst_certificate", "udyam_certificate", "signatory_id", "address_proof"]


def _f(**kw):
    return {k: {"value": v, "conf": 95.0} for k, v in kw.items()}


def fake_docs(store, gstin, bill_date=None, drop=(), conf=95.0, sig_biz=None, ap_state=None,
              id_valid="2029-01-01", gst_legal=None):
    g = store.gstin[gstin]
    u = store.udyam_for_gstin(g)
    name = g["trade_name"]
    city = g["principal_place_of_business"].split(",")[-2].strip()
    addr_state = ap_state or g["state"]
    bill = bill_date or (config.TODAY - timedelta(days=10)).isoformat()
    docs = {
        "gst_certificate": {"fields": _f(gstin=gstin, legal_name=gst_legal or g["legal_name"],
                                         trade_name=name,
                                         address=g["principal_place_of_business"]),
                            "confidence": conf, "gstin_candidates": [gstin]},
        "udyam_certificate": {"fields": _f(udyam=(u or {}).get("udyam_number", "UDYAM-XX-00-0000000"),
                                           enterprise_name=name, city=city, state=g["state"]),
                              "confidence": conf, "gstin_candidates": []},
        "signatory_id": {"fields": _f(name="Test Person", for_business=sig_biz or name,
                                      valid_till=id_valid), "confidence": conf, "gstin_candidates": []},
        "address_proof": {"fields": _f(billed_to=name, date=bill,
                                       address=f"Shop 1, Road, {city}, {addr_state} - 123456"),
                          "confidence": conf, "gstin_candidates": []},
    }
    return {k: v for k, v in docs.items() if k not in drop}


@pytest.fixture
def run(monkeypatch, store):
    def _run(gstin, typed=True, **kw):
        docs = fake_docs(store, gstin, **kw)
        monkeypatch.setattr(ocr, "read_document", lambda path, doc_type: docs[doc_type])
        present = {d: f"/fake/{d}.png" for d in docs}
        return validate.validate_present("T", present, typed_gstin=gstin if typed else None)
    return _run


def an_active(store, state=None):
    for g, r in store.gstin.items():
        if r["status"] == "Active" and (state is None or r["state"] == state) \
                and store.udyam_for_gstin(r):
            return g


def with_status(store, status):
    for g, r in store.gstin.items():
        if r["status"] == status and store.udyam_for_gstin(r):
            return g


def test_clean_applicant_is_approved(run, store):
    r = run(an_active(store))
    assert r["decision"] == "APPROVE", r["reasons"]


@pytest.mark.parametrize("offset,expect", [(90, "APPROVE"), (91, "REJECT"), (0, "APPROVE"), (-1, "REJECT")])
def test_address_proof_90_day_boundary(run, store, offset, expect):
    d = (config.TODAY - timedelta(days=offset)).isoformat()
    r = run(an_active(store), bill_date=d)
    assert r["decision"] == expect, r["reasons"]


def test_earliest_valid_bill_date_is_2026_04_16(run, store):
    assert run(an_active(store), bill_date="2026-04-16")["decision"] == "APPROVE"
    assert run(an_active(store), bill_date="2026-04-15")["decision"] == "REJECT"


@pytest.mark.parametrize("status", ["Cancelled", "Suspended"])
def test_non_active_gstin_rejected_typed_and_ocr_resolved(run, store, status):
    g = with_status(store, status)
    for typed in (True, False):
        r = run(g, typed=typed)
        assert r["decision"] == "REJECT"
        assert any(status.lower() in x["reason"].lower() for x in r["reasons"])


@pytest.mark.parametrize("missing", DOC_TYPES)
def test_missing_any_required_document_rejects(run, store, missing):
    r = run(an_active(store), drop=(missing,))
    assert r["decision"] == "REJECT"
    assert any(missing.replace("_", " ") in x["reason"] for x in r["reasons"])


def test_state_mismatch_between_certificate_and_address_proof_rejects(run, store):
    g = an_active(store, "Maharashtra")
    r = run(g, ap_state="Gujarat")
    assert r["decision"] == "REJECT"
    assert any("state mismatch" in x["reason"] for x in r["reasons"])


def test_strong_business_name_mismatch_rejects_when_confident(run, store):
    r = run(an_active(store), sig_biz="Completely Different Traders")
    assert r["decision"] == "REJECT"


def test_soft_name_difference_only_routes_to_review(run, store):
    g = an_active(store)
    name = store.gstin[g]["trade_name"]
    r = run(g, sig_biz=name[: int(len(name) * 0.8)] + "xx")       # ~0.7-0.85 similarity
    assert r["decision"] in ("REVIEW", "APPROVE")                 # never an auto-reject on a near-miss


def test_low_confidence_alone_never_rejects(run, store):
    r = run(an_active(store), conf=60.0)
    assert r["decision"] == "REVIEW"


def test_expired_signatory_id_rejects(run, store):
    assert run(an_active(store), id_valid="2026-07-01")["decision"] == "REJECT"


def test_typed_gstin_not_in_registry_rejects(run, store, monkeypatch):
    docs = fake_docs(store, an_active(store))
    monkeypatch.setattr(ocr, "read_document", lambda path, doc_type: docs[doc_type])
    r = validate.validate_present("T", {d: "x" for d in docs}, typed_gstin="27ABCXD1234E1Z5")
    assert r["decision"] == "REJECT"


def test_identifiers_are_masked_in_response_and_reasons(run, store):
    g = with_status(store, "Cancelled")
    r = run(g)
    blob = str(r)
    assert g not in blob and g[-4:] in blob
    for d in r["extracted"].values():
        for k, v in d["fields"].items():
            if k in ("gstin", "udyam", "id_no", "consumer_no"):
                assert v["value"].startswith("*") or len(v["value"]) <= 4


def test_stp_rate_is_share_of_auto_approvals(monkeypatch, store, tmp_path):
    for a in ("K01", "K02"):
        for d in DOC_TYPES:
            (tmp_path / f"{a}_{d}.png").write_bytes(b"x")
    ok = {"decision": "APPROVE"}, {"decision": "REJECT"}
    seq = iter(ok)
    monkeypatch.setattr(validate, "validate_present", lambda *a, **k: next(seq))
    r = validate.validate_all(str(tmp_path))
    assert r["stp_rate"] == 50.0 and r["total"] == 2 and r["approved"] == 1


# ------------------------------------------------- real OCR on the specimens
SPECIMENS = os.path.join(config.DATA_DIR, "kyc_documents")
has_specimens = bool(glob.glob(os.path.join(SPECIMENS, "K01_*.png")))
real = pytest.mark.skipif(not (has_specimens and ocr._HAVE_OCR), reason="specimens/tesseract missing")


@pytest.fixture(scope="module")
def batch():
    return {r["applicant"]: r for r in validate.validate_all(SPECIMENS)["results"]}


@real
def test_specimens_planted_problems_are_caught(batch):
    assert batch["K01"]["decision"] == "REJECT"
    assert any("Cancelled" in x["reason"] for x in batch["K01"]["reasons"])
    assert batch["K05"]["decision"] == "REJECT"
    assert any("udyam certificate" in x["reason"] for x in batch["K05"]["reasons"])
    assert batch["K11"]["decision"] == "REJECT"
    assert any("257 days" in x["reason"] for x in batch["K11"]["reasons"])


@real
def test_specimen_name_mismatch_and_unreadable_cert_go_to_review(batch):
    assert batch["K07"]["decision"] == "REVIEW"
    assert any("Shri Physio Clinic" in x["reason"] for x in batch["K07"]["reasons"])
    assert batch["K04"]["decision"] == "REVIEW"           # blurred certificate: never a false reject


@real
def test_specimens_clean_applicants_are_approved_and_stp_is_reported(batch):
    clean = [k for k, r in batch.items() if k not in {"K01", "K04", "K05", "K07", "K11"}]
    assert all(batch[k]["decision"] == "APPROVE" for k in clean), \
        {k: batch[k]["reasons"] for k in clean if batch[k]["decision"] != "APPROVE"}
    stp = sum(r["decision"] == "APPROVE" for r in batch.values()) / len(batch) * 100
    assert round(stp, 1) == round(validate.validate_all(SPECIMENS)["stp_rate"], 1)


@real
def test_typed_gstin_path_on_specimens(store):
    present = {os.path.basename(p).split("_", 1)[1][:-4]: p
               for p in glob.glob(os.path.join(SPECIMENS, "K02_*.png"))}
    g = next(k for k, v in store.gstin.items() if v["trade_name"] == "Harmony Dental Care"
             and v["state"] == "West Bengal")
    assert validate.validate_present("K02", present, typed_gstin=g)["decision"] == "APPROVE"
    other = next(k for k, v in store.gstin.items() if v["state"] == "Gujarat" and v["status"] == "Active")
    assert validate.validate_present("K02", present, typed_gstin=other)["decision"] == "REJECT"
