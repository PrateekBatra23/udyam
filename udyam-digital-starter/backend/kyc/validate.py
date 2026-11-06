"""Smart KYC validation + 3-way decision + STP (sections 6 + O4).

Every check is derived from the documents, the registries and TODAY; nothing is
keyed on an applicant id. Three outcomes:
  REJECT  any HARD fail: missing required document, GSTIN not in registry or
          not Active (on a reliably-known GSTIN), stale/future address proof,
          expired signatory ID, certificate belongs to a different GSTIN,
          confidently-read business-name or state/city mismatch.
  APPROVE every check passes and mean OCR confidence >= threshold.
  REVIEW  everything else - low confidence, unreadable GSTIN, soft name match.
          OCR fuzziness alone never rejects.

Each check carries `severity` (ok | review | fail), the `doc` it came from and a
human-readable `detail`. Identifiers in the response are masked (last 4).
"""
import glob
import os
import re
from datetime import date

import config
import privacy
from data_store import get_store
from kyc import ocr, lookups, names
from rules import identifiers

REQUIRED_DOCS = ["gst_certificate", "udyam_certificate", "signatory_id", "address_proof"]
CONF_OK = config.OCR_AUTO_APPROVE_CONFIDENCE      # field/doc confidence treated as "reliable"
_ID_FIELDS = {"gstin", "udyam", "id_no", "consumer_no"}


# --------------------------------------------------------------------- utils
def _fv(ext: dict, doc: str, key: str):
    return ((ext.get(doc) or {}).get("fields", {}).get(key) or {}).get("value")


def _fc(ext: dict, doc: str, key: str) -> float:
    return ((ext.get(doc) or {}).get("fields", {}).get(key) or {}).get("conf", 0.0)


def _parse_date(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _split_address(addr: str):
    """'Shop/Unit 1, Tech Park Road, Visakhapatnam, A ndhra Pradesh - 118383'
    -> (city, state) using the registry's own state list to absorb OCR spacing."""
    if not addr:
        return None, None
    body = re.sub(r"\s*-\s*\d[\d ]*$", "", addr.strip())
    parts = [p.strip() for p in body.split(",") if p.strip()]
    state_raw = parts[-1] if parts else ""
    city_raw = parts[-2] if len(parts) > 1 else ""
    # OCR sometimes splits one word across the comma-less break ("Ludhi ana")
    key = state_raw.replace(" ", "").lower()
    state = None
    for st in lookups.known_states():
        if key and (key == st.replace(" ", "").lower() or
                    lookups.lev(key, st.replace(" ", "").lower()) <= 2):
            state = st
            break
    return city_raw.replace(" ", "").lower() or None, state


def _city_match(a, b) -> bool:
    if not a or not b:
        return True      # nothing to compare
    a, b = a.replace(" ", "").lower(), b.replace(" ", "").lower()
    return lookups.lev(a, b) <= 2


def _mask_output(extracted: dict) -> dict:
    out = {}
    for doc, d in extracted.items():
        fields = {}
        for k, v in d["fields"].items():
            val = privacy.mask(v["value"]) if k in _ID_FIELDS else v["value"]
            fields[k] = {"value": val, "conf": v["conf"]}
        out[doc] = {"fields": fields, "confidence": d["confidence"], "variant": d.get("variant")}
    return out


def _mask_in_text(text: str, secrets: list) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, privacy.mask(s))
    return text


# ----------------------------------------------------------------- the core
def validate_present(applicant: str, present: dict,
                     typed_gstin: str | None = None,
                     typed_udyam: str | None = None) -> dict:
    """`present` is {doc_type: image_path} for ONE applicant."""
    checks = []

    def add(check, severity, detail, doc=None):
        checks.append({"check": check, "pass": severity == "ok", "severity": severity,
                       "doc": doc, "detail": detail})

    typed_gstin = (typed_gstin or "").strip().upper() or None
    typed_udyam = (typed_udyam or "").strip().upper() or None

    # 0. completeness ------------------------------------------------------
    missing = [d for d in REQUIRED_DOCS if d not in present]
    if missing:
        add("documents_present", "fail",
            "missing required document(s): " + ", ".join(m.replace("_", " ") for m in missing))
    else:
        add("documents_present", "ok", "all 4 required documents supplied")

    # 1. OCR every supplied document --------------------------------------
    ext = {doc: ocr.read_document(path, doc) for doc, path in present.items()}
    confs = [e["confidence"] for e in ext.values()]
    mean_conf = round(sum(confs) / len(confs), 1) if confs else 0.0

    gst = ext.get("gst_certificate")
    gst_trade = _fv(ext, "gst_certificate", "trade_name")
    gst_legal = _fv(ext, "gst_certificate", "legal_name")
    proprietor, gst_legal_biz = names.split_proprietor(gst_legal) if gst_legal else (None, None)
    ud_name = _fv(ext, "udyam_certificate", "enterprise_name")
    sig_biz = _fv(ext, "signatory_id", "for_business")
    billed_to = _fv(ext, "address_proof", "billed_to")
    name_hints = [gst_trade, gst_legal_biz, ud_name, sig_biz, billed_to]

    # 2. GSTIN: typed value is the source of truth --------------------------
    gstin_truth, gstin_src, secrets = None, None, [typed_gstin, typed_udyam]
    registry_row = None
    if typed_gstin:
        gstin_truth, gstin_src = typed_gstin, "typed"
    elif gst:
        res = lookups.resolve_gstin_from_ocr(gst.get("gstin_candidates", []), name_hints)
        if res.get("gstin"):
            gstin_truth, gstin_src = res["gstin"], f"ocr-resolved ({res['method']})"

    if gstin_truth:
        secrets.append(gstin_truth)
        fmt = identifiers.gstin_format_ok(gstin_truth) and identifiers.gstin_checksum_ok(gstin_truth)
        st = lookups.gstin_status(gstin_truth)
        if not fmt:
            add("gstin_format", "fail" if gstin_src == "typed" else "review",
                f"GSTIN {privacy.mask(gstin_truth)} fails format/checksum", "gst_certificate")
        if not st.get("found"):
            add("gstin_registry", "fail" if gstin_src == "typed" else "review",
                f"GSTIN {privacy.mask(gstin_truth)} ({gstin_src}) not found in the GST registry",
                "gst_certificate")
        elif (st.get("status") or "").lower() != "active":
            registry_row = get_store().gstin_lookup(gstin_truth)
            add("gstin_status", "fail",
                f"GSTIN {privacy.mask(gstin_truth)} ({gstin_src}) is {st['status']} in the GST "
                f"registry - only Active registrations can be onboarded", "gst_certificate")
        else:
            registry_row = get_store().gstin_lookup(gstin_truth)
            add("gstin_status", "ok",
                f"GSTIN {privacy.mask(gstin_truth)} ({gstin_src}) is Active", "gst_certificate")
        if st.get("found") and not (registry_row or {}):
            registry_row = get_store().gstin_lookup(gstin_truth)
    else:
        add("gstin_status", "review",
            "GSTIN on the certificate could not be read reliably and none was typed - "
            "routed to manual review (OCR noise is not grounds for rejection)",
            "gst_certificate")

    # 2b. cross-check the certificate's own GSTIN against the typed one -----
    if typed_gstin and gst and gst.get("gstin_candidates"):
        known = set(get_store().gstin)
        best = min((lookups.lev(c, typed_gstin), c) for c in gst["gstin_candidates"])
        if best[0] <= 3:
            add("certificate_matches_typed_gstin", "ok",
                f"certificate reads as {privacy.mask(best[1])} (distance {best[0]} from typed - "
                "OCR noise tolerated)", "gst_certificate")
        else:
            other, _ = identifiers.correct_gstin_ocr(best[1], known)
            if other in known and other != typed_gstin and identifiers.gstin_checksum_ok(other):
                add("certificate_matches_typed_gstin", "fail",
                    f"certificate belongs to a different registered GSTIN "
                    f"({privacy.mask(other)})", "gst_certificate")
            else:
                add("certificate_matches_typed_gstin", "review",
                    "certificate GSTIN could not be confirmed against the typed GSTIN",
                    "gst_certificate")

    # 3. Udyam ---------------------------------------------------------------
    if "udyam_certificate" in present:
        ud_val = typed_udyam or ocr.normalise_udyam(_fv(ext, "udyam_certificate", "udyam"))
        if ud_val:
            secrets.append(ud_val)
        ust = lookups.udyam_status(ud_val) if ud_val else {"found": False}
        fmt_ok = bool(ud_val) and identifiers.udyam_format_ok(ud_val)
        if not ud_val:
            blank = ext["udyam_certificate"]["confidence"] >= CONF_OK
            add("udyam_registry", "fail" if blank else "review",
                "the Udyam certificate shows no registration number" if blank
                else "Udyam number could not be read", "udyam_certificate")
        elif not fmt_ok:
            add("udyam_registry", "review", "Udyam number badly formed / misread",
                "udyam_certificate")
        elif not ust.get("found"):
            add("udyam_registry", "fail" if typed_udyam else "review",
                f"Udyam {privacy.mask(ud_val)} not found in the Udyam registry",
                "udyam_certificate")
        else:
            add("udyam_registry", "ok", f"Udyam {privacy.mask(ud_val)} found in registry",
                "udyam_certificate")
            if registry_row:
                us = ust.get("state")
                if us and registry_row.get("state") and us != registry_row["state"]:
                    add("udyam_state_vs_gst", "fail",
                        f"Udyam registered in {us} but GSTIN registered in {registry_row['state']}",
                        "udyam_certificate")

    # 4. address-proof freshness (hard) ---------------------------------------
    if "address_proof" in present:
        d = _parse_date(ocr.normalise_date(_fv(ext, "address_proof", "date")))
        if d is None:
            add("address_proof_freshness", "review", "bill date unreadable", "address_proof")
        else:
            age = (config.TODAY - d).days
            if 0 <= age <= config.ADDRESS_PROOF_MAX_AGE_DAYS:
                add("address_proof_freshness", "ok",
                    f"bill dated {d} is {age} days old (limit {config.ADDRESS_PROOF_MAX_AGE_DAYS})",
                    "address_proof")
            else:
                why = "dated in the future" if age < 0 else \
                    f"is {age} days old (limit {config.ADDRESS_PROOF_MAX_AGE_DAYS}; "\
                    f"must be dated on/after {config.TODAY.fromordinal(config.TODAY.toordinal() - config.ADDRESS_PROOF_MAX_AGE_DAYS)})"
                add("address_proof_freshness", "fail", f"address proof {d} {why}", "address_proof")

    # 5. signatory ID validity -------------------------------------------------
    if "signatory_id" in present:
        vt = _parse_date(ocr.normalise_date(_fv(ext, "signatory_id", "valid_till")))
        if vt is None:
            add("signatory_id_valid", "review", "ID validity date unreadable", "signatory_id")
        elif vt < config.TODAY:
            add("signatory_id_valid", "fail", f"signatory ID expired on {vt}", "signatory_id")
        else:
            add("signatory_id_valid", "ok", f"signatory ID valid till {vt}", "signatory_id")

    # 6. state / city consistency ---------------------------------------------
    ap_city, ap_state = _split_address(_fv(ext, "address_proof", "address"))
    gc_city, gc_state = _split_address(_fv(ext, "gst_certificate", "address"))
    ref_state = (registry_row or {}).get("state")
    ref_city = None
    if registry_row:
        ref_city, _ = _split_address(registry_row.get("principal_place_of_business"))
    if gstin_truth and lookups.state_code_map().get(gstin_truth[:2]) and not ref_state:
        ref_state = lookups.state_code_map()[gstin_truth[:2]]
    ud_state = _fv(ext, "udyam_certificate", "state")
    states = {"address proof": ap_state, "GST certificate": gc_state,
              "Udyam certificate": ud_state, "GST registry": ref_state}
    states = {k: v for k, v in states.items() if v}
    if ap_state and len(states) > 1:
        bad = {k: v for k, v in states.items() if v != ap_state and k != "address proof"}
        if bad:
            reliable = _fc(ext, "address_proof", "address") >= CONF_OK
            add("state_consistency", "fail" if reliable else "review",
                "state mismatch: address proof says " + ap_state + "; " +
                "; ".join(f"{k} says {v}" for k, v in bad.items()), "address_proof")
        else:
            add("state_consistency", "ok", f"state agrees across documents ({ap_state})",
                "address_proof")
    if ap_city:
        cities = [c for c in (gc_city, ref_city,
                              (_fv(ext, "udyam_certificate", "city") or "").replace(" ", "").lower() or None)
                  if c]
        if cities and not all(_city_match(ap_city, c) for c in cities):
            add("city_consistency", "review",
                "city on the address proof differs from the registered city", "address_proof")

    # 7. business-name consistency --------------------------------------------
    ref_name = None
    if registry_row:
        ref_name = names.split_proprietor(registry_row.get("legal_name"))[1]
    ref_label = "GST registry" if ref_name else None
    if not ref_name:
        ref_name, ref_label = ud_name or gst_trade or sig_biz, "first available document"
    pairs = [("GST certificate (legal name)", gst_legal_biz, _fc(ext, "gst_certificate", "legal_name"), "gst_certificate"),
             ("GST certificate (trade name)", gst_trade, _fc(ext, "gst_certificate", "trade_name"), "gst_certificate"),
             ("Udyam certificate", ud_name, _fc(ext, "udyam_certificate", "enterprise_name"), "udyam_certificate"),
             ("signatory ID (for business)", sig_biz, _fc(ext, "signatory_id", "for_business"), "signatory_id"),
             ("address proof (billed to)", billed_to, _fc(ext, "address_proof", "billed_to"), "address_proof")]
    if ref_name:
        for label, val, conf, doc in pairs:
            if not val:
                continue
            r = names.ratio(ref_name, val)
            v = names.verdict(r)
            if v == "match":
                continue
            sev = "fail" if (v == "mismatch" and conf >= CONF_OK) else "review"
            add("business_name_consistency", sev,
                f"{label} reads '{val}' but {ref_label} says '{ref_name}' "
                f"(similarity {r:.2f}; match>={config.NAME_MATCH}, mismatch<{config.NAME_REVIEW})", doc)
        if not any(c["check"] == "business_name_consistency" for c in checks):
            add("business_name_consistency", "ok",
                f"business name agrees across documents ('{ref_name}')")
    # proprietor vs signatory person
    sig_name = _fv(ext, "signatory_id", "name")
    if proprietor and sig_name:
        r = names.ratio(proprietor, sig_name)
        if r < config.NAME_MATCH:
            sev = "fail" if (r < config.NAME_REVIEW and _fc(ext, "signatory_id", "name") >= CONF_OK) else "review"
            add("signatory_vs_proprietor", sev,
                f"signatory '{sig_name}' differs from proprietor '{proprietor}' (similarity {r:.2f})",
                "signatory_id")

    # 8. confidence --------------------------------------------------------------
    conf_ok = mean_conf >= config.OCR_AUTO_APPROVE_CONFIDENCE
    add("ocr_confidence", "ok" if conf_ok else "review",
        f"mean OCR confidence {mean_conf} (auto-approve threshold {config.OCR_AUTO_APPROVE_CONFIDENCE})")

    # decision ----------------------------------------------------------------------
    fails = [c for c in checks if c["severity"] == "fail"]
    reviews = [c for c in checks if c["severity"] == "review"]
    decision = "REJECT" if fails else ("REVIEW" if reviews else "APPROVE")
    for c in checks:
        c["detail"] = _mask_in_text(c["detail"], secrets)

    return {"applicant": applicant, "decision": decision, "mean_confidence": mean_conf,
            "reasons": [{"severity": c["severity"], "doc": c["doc"], "reason": c["detail"]}
                        for c in fails + reviews],
            "checks": checks, "extracted": _mask_output(ext),
            "gstin_source": gstin_src, "gstin_masked": privacy.mask(gstin_truth) if gstin_truth else None}


# ------------------------------------------------------------------- helpers
def _doc_type(path: str) -> str:
    return os.path.basename(path).split("_", 1)[1].rsplit(".", 1)[0]


def validate_applicant(applicant_dir: str, typed_gstin=None, typed_udyam=None) -> dict:
    applicant = os.path.basename(applicant_dir.rstrip("/\\")) or "applicant"
    present = {_doc_type(p): p for p in glob.glob(os.path.join(applicant_dir, "*.png"))}
    return validate_present(applicant, present, typed_gstin, typed_udyam)


def validate_all(kyc_root: str, typed: dict | None = None) -> dict:
    """Run every applicant Kxx in a flat folder and compute the STP rate.
    `typed` optionally maps applicant -> typed GSTIN."""
    typed = typed or {}
    applicants = sorted({os.path.basename(p).split("_")[0]
                         for p in glob.glob(os.path.join(kyc_root, "*.png"))})
    results = []
    for a in applicants:
        present = {_doc_type(p): p for p in glob.glob(os.path.join(kyc_root, f"{a}_*.png"))}
        results.append(validate_present(a, present, typed_gstin=typed.get(a)))
    n = len(results)
    count = lambda d: sum(1 for r in results if r["decision"] == d)
    return {"stp_rate": round(count("APPROVE") / n * 100, 1) if n else 0.0,
            "approved": count("APPROVE"), "review": count("REVIEW"),
            "rejected": count("REJECT"), "total": n, "results": results}
