"""Smart KYC validation + 3-way decision + STP (sections 6 + O4).

decision:
  - any HARD fail (cancelled/suspended GSTIN, stale/missing address proof,
    missing required doc, name mismatch < NAME_REVIEW) -> REJECT
  - all checks pass AND mean confidence >= threshold                -> APPROVE
  - otherwise (low confidence, soft name mismatch)                  -> REVIEW
"""
import os
import glob
from datetime import date
from difflib import SequenceMatcher

import config
from kyc import ocr, lookups
from rules import identifiers

REQUIRED_DOCS = {"gst_certificate", "udyam_certificate", "signatory_id", "address_proof"}


def _norm_name(s: str) -> str:
    if not s:
        return ""
    s = s.lower()
    for suf in ["pvt ltd", "private limited", "llp", "ltd", "prop.", "prop",
                "(prop.", ")", "(", "."]:
        s = s.replace(suf, " ")
    return " ".join(s.split())


def _name_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm_name(a), _norm_name(b)).ratio()


def _parse_date(s: str):
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _files_for(applicant_dir: str) -> dict:
    """{doc_type: path} for one applicant's folder."""
    return {os.path.basename(p).split("_", 1)[1].replace(".png", ""): p
            for p in glob.glob(os.path.join(applicant_dir, "*.png"))}


def validate_present(applicant: str, present: dict,
                     typed_gstin: str | None = None,
                     typed_udyam: str | None = None) -> dict:
    """Core validator. `present` is {doc_type: image_path} for ONE applicant."""
    checks, confidences = [], []
    hard_fail, soft_review = False, False

    # 1. completeness
    missing = REQUIRED_DOCS - set(present)
    if missing:
        hard_fail = True
        checks.append({"check": "documents_present", "pass": False,
                       "detail": f"missing: {', '.join(sorted(missing))}"})
    else:
        checks.append({"check": "documents_present", "pass": True, "detail": "all 4 present"})

    # OCR each present doc
    extracted = {}
    for doc, path in present.items():
        text, conf = ocr.ocr_text_and_confidence(path)
        confidences.append(conf)
        extracted[doc] = {"fields": ocr.extract_fields(text), "confidence": round(conf, 1)}

    # 2. GSTIN. The TYPED value is authoritative; OCR is only a fallback.
    #    Key rule (spec O4): an unreadable/unresolvable GSTIN from OCR is
    #    *uncertainty* -> REVIEW, NOT a rejection. We only hard-fail when we have
    #    a reliable GSTIN (typed, or OCR repaired to a real registry match) whose
    #    registry status is not Active, or when a TYPED id is absent from registry.
    gstin_truth = typed_gstin
    from_typed = bool(typed_gstin)
    if "gst_certificate" in present and not gstin_truth:
        raw = extracted["gst_certificate"]["fields"].get("gstin") or ""
        from data_store import get_store
        corrected, was_corr = identifiers.correct_gstin_ocr(raw, set(get_store().gstin))
        gstin_truth = corrected
    if gstin_truth:
        fmt_ok = identifiers.gstin_format_ok(gstin_truth) and identifiers.gstin_checksum_ok(gstin_truth)
        st = lookups.gstin_status(gstin_truth)
        status = (st.get("status") or "").lower()
        if st.get("found"):
            ok = status == "active"
            if not ok:
                hard_fail = True            # genuine: cancelled/suspended registration
        else:
            ok = False
            if from_typed:
                hard_fail = True            # user typed a GSTIN not in the registry
            else:
                soft_review = True          # OCR couldn't resolve -> review, don't reject
        checks.append({"check": "gstin", "pass": ok,
                       "detail": f"value={gstin_truth} source={'typed' if from_typed else 'ocr'} "
                                 f"format={fmt_ok} found={st.get('found')} status={st.get('status')}"})
    else:
        soft_review = True
        checks.append({"check": "gstin", "pass": False, "detail": "no readable GSTIN -> review"})

    # 3. Udyam
    udyam_val = typed_udyam or extracted.get("udyam_certificate", {}).get("fields", {}).get("udyam")
    if "udyam_certificate" in present:
        ust = lookups.udyam_status(udyam_val) if udyam_val else {"found": False}
        ok = bool(udyam_val and identifiers.udyam_format_ok(udyam_val) and ust.get("found"))
        if not ok:
            soft_review = True
        checks.append({"check": "udyam", "pass": ok,
                       "detail": f"value={udyam_val} found={ust.get('found')}"})

    # 4. address-proof freshness
    if "address_proof" in present:
        ap = extracted["address_proof"]["fields"].get("date")
        d = _parse_date(ap) if ap else None
        if d:
            age = (config.TODAY - d).days
            ok = 0 <= age <= config.ADDRESS_PROOF_MAX_AGE_DAYS
            if not ok:
                hard_fail = True
            checks.append({"check": "address_proof_freshness", "pass": ok,
                           "detail": f"date={ap} age={age}d (max {config.ADDRESS_PROOF_MAX_AGE_DAYS})"})
        else:
            soft_review = True
            checks.append({"check": "address_proof_freshness", "pass": False,
                           "detail": "no readable date -> review"})

    # 5. cross-document business-name consistency. Compare the GST legal/trade
    #    name to the signatory card's "For business" field (NOT the person's
    #    name). A mismatch routes to REVIEW rather than auto-reject, because OCR
    #    field extraction is noisy — a human confirms the genuine mismatches.
    gst_name = (extracted.get("gst_certificate", {}).get("fields", {}).get("legal_name")
                or extracted.get("gst_certificate", {}).get("fields", {}).get("trade_name"))
    if not gst_name and gstin_truth:
        gst_name = lookups.gstin_status(gstin_truth).get("legal_name")
    sig_biz = extracted.get("signatory_id", {}).get("fields", {}).get("for_business")
    if gst_name and sig_biz:
        r = _name_ratio(gst_name, sig_biz)
        verdict = r >= config.NAME_REVIEW
        if not verdict:
            soft_review = True              # flag for human review, do not hard-reject
        checks.append({"check": "business_name_consistency", "pass": verdict,
                       "detail": f"gst='{gst_name}' signatory_for='{sig_biz}' ratio={round(r, 2)}"})

    mean_conf = round(sum(confidences) / len(confidences), 1) if confidences else 0.0
    if hard_fail:
        decision = "REJECT"
    elif mean_conf >= config.OCR_AUTO_APPROVE_CONFIDENCE and not soft_review:
        decision = "APPROVE"
    else:
        decision = "REVIEW"

    return {"applicant": applicant, "decision": decision, "mean_confidence": mean_conf,
            "checks": checks, "extracted": extracted}


def validate_applicant(applicant_dir: str, typed_gstin=None, typed_udyam=None) -> dict:
    applicant = os.path.basename(applicant_dir.rstrip("/")) or "applicant"
    return validate_present(applicant, _files_for(applicant_dir), typed_gstin, typed_udyam)


def validate_all(kyc_root: str) -> dict:
    """Run every applicant Kxx in a flat folder and compute the STP rate."""
    applicants = sorted({os.path.basename(p).split("_")[0]
                         for p in glob.glob(os.path.join(kyc_root, "*.png"))})
    results = []
    for a in applicants:
        present = {os.path.basename(p).split("_", 1)[1].replace(".png", ""): p
                   for p in glob.glob(os.path.join(kyc_root, f"{a}_*.png"))}
        results.append(validate_present(a, present))
    approved = sum(1 for r in results if r["decision"] == "APPROVE")
    return {"stp_rate": round(approved / len(results) * 100, 1) if results else 0.0,
            "approved": approved, "total": len(results), "results": results}
