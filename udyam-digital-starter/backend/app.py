"""FastAPI entry point. Loads data on startup and wires every endpoint from the
spec's endpoint->module map (section 15)."""
import glob
import logging
import os
import re
import shutil
import tempfile
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
import db
import privacy
from data_store import get_store, city_of
from rules import identifiers
from rules.eligibility import Profile, validate_bundle
from rules.quote import build_quote
from advisor import agent, fallback
from advisor.segment import infer_segment
from kyc import validate as kyc_validate, lookups
from tracker import orders
from propensity import score as propensity
import analytics
import demo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("udyam")

app = FastAPI(title="Project Udyam Digital API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

KYC_SLOTS = ["gst_certificate", "udyam_certificate", "signatory_id", "address_proof"]


@app.on_event("startup")
def _startup():
    get_store()   # load reference CSVs into memory once
    db.init_db()  # create Postgres tables for orders + consent if absent


# ---------- models ----------
class RecommendReq(BaseModel):
    gstin: Optional[str] = None            # verified server-side; the client's flag is ignored
    profile: dict = {}
    current_spend: Optional[int] = None
    language: str = "en"
    priority: Optional[str] = None
    requested: Optional[list[str]] = None  # product ids the owner asked for
    message: Optional[str] = None          # free-text request ("add a leased line")


class QuoteReq(BaseModel):
    segment: str
    num_sites: int = 1
    bundle: list[str]
    qty: Optional[dict] = None
    current_spend: Optional[int] = None
    price_mode: str = "auto"
    profile: Optional[dict] = None         # if given, eligibility is re-checked


class OrderReq(BaseModel):
    bundle: list[str]
    qty: Optional[dict] = None
    gstin: Optional[str] = None
    profile: dict = {}
    price_mode: str = "auto"
    current_spend: Optional[int] = None


class ScoreReq(BaseModel):
    lead: dict


# ---------- helpers ----------
def _verified_profile(gstin: Optional[str], raw: dict) -> Profile:
    """Build the eligibility Profile. GSTIN status comes from the registry, never
    from the client."""
    d = dict(raw or {})
    active = False
    if gstin:
        g = get_store().gstin_lookup(gstin.strip().upper())
        active = bool(g and str(g.get("status")).lower() == "active"
                      and identifiers.gstin_checksum_ok(gstin.strip().upper()))
    d["has_active_gstin"] = active
    return Profile.from_dict(d)


def require_consent(receipt: Optional[str]):
    """DPDP: no KYC collection before a consent receipt exists (O8)."""
    if not receipt or not privacy.get_consent(receipt):
        raise HTTPException(403, "Consent required before KYC: accept the consent notice first "
                                 "(POST /privacy/consent) and send the receipt id.")


# ---------- basic ----------
@app.get("/health")
def health():
    s = get_store()
    return {"ok": True, "products": len(s.products), "gstin": len(s.gstin),
            "udyam": len(s.udyam), "leads": len(s.leads), "today": str(config.TODAY),
            "llm": config.USE_LLM}


@app.get("/catalogue")
def catalogue():
    return get_store().catalogue.fillna("").to_dict("records")


# ---------- O1 onboarding ----------
@app.get("/gstin/{gstin}")
def gstin(gstin: str):
    r = lookups.gstin_status(gstin.upper())
    if not r.get("found"):
        raise HTTPException(404, "GSTIN not found")
    return r


@app.get("/udyam/{udyam}")
def udyam(udyam: str):
    r = lookups.udyam_status(udyam.upper())
    if not r.get("found"):
        raise HTTPException(404, "Udyam not found")
    return r


@app.get("/onboard")
def onboard(gstin: str = Query(...), udyam: Optional[str] = None):
    """GSTIN-first autofill. Returns the business card, an inferred (confirmable)
    segment and priors for the fields the registry does not carry."""
    store = get_store()
    gstin = gstin.strip().upper()
    if not (identifiers.gstin_format_ok(gstin) and identifiers.gstin_checksum_ok(gstin)):
        raise HTTPException(422, "That GSTIN is not valid (format or checksum). Please re-check it.")
    g = store.gstin_lookup(gstin)
    if not g:
        raise HTTPException(404, "GSTIN not found in the registry")

    status = g.get("status")
    u = store.udyam_lookup(udyam.strip().upper()) if udyam else store.udyam_for_gstin(g)
    seg = infer_segment(g, u)
    city = city_of(g.get("principal_place_of_business"))
    tier, tier_known = store.city_tier(city)
    accepted = str(status).lower() == "active"
    out = {
        "gstin": gstin,
        "accepted": accepted,
        "reject_reason": None if accepted else
            f"This GSTIN is {status} in the GST registry. Only Active registrations can be onboarded.",
        "legal_name": g.get("legal_name"),
        "trade_name": g.get("trade_name"),
        "constitution": g.get("constitution"),
        "state": g.get("state"),
        "city": city,
        "city_tier": tier, "city_tier_known": tier_known,
        "principal_place_of_business": g.get("principal_place_of_business"),
        "registration_date": g.get("registration_date"),
        "status": status,
        "udyam": None if not u else {
            "udyam_number": u["udyam_number"], "enterprise_type": u["enterprise_type"],
            "major_activity": u["major_activity"], "nic_description": u["nic_description"]},
        "inferred_segment": seg,           # {segment, confidence, basis} - the owner confirms
        "employee_prior": store.employee_prior.get(seg["segment"], 5),
        "sites_prior": store.sites_prior.get(seg["segment"], 1),
        "autofilled_fields": sum(v not in (None, "") for v in
                                 [g.get("legal_name"), g.get("trade_name"), g.get("constitution"),
                                  g.get("state"), city, tier, g.get("principal_place_of_business"),
                                  seg["segment"], u and u["enterprise_type"], u and u["major_activity"]]),
    }
    log.info("onboard gstin=%s status=%s segment=%s", privacy.mask(gstin), status, seg["segment"])
    return out


@app.get("/demo/profiles")
def demo_profiles():
    """The five pinned test profiles (real registry identifiers) for the demo."""
    return demo.profiles()


# ---------- O2 advisor ----------
@app.get("/advisor/questions")
def advisor_questions(segment: str = "micro", lang: str = "en",
                      num_sites: Optional[int] = None, current_spend: Optional[int] = None,
                      priority: Optional[str] = None):
    known = {"num_sites": num_sites, "current_spend": current_spend, "priority": priority}
    return fallback.questions(Profile(segment=segment), lang, known)


@app.post("/advisor/recommend")
def recommend(req: RecommendReq):
    profile = _verified_profile(req.gstin, req.profile)
    return agent.recommend(profile.__dict__, req.current_spend, req.language,
                           req.priority, req.requested, req.message)


# ---------- O3 quote ----------
@app.post("/quote")
def quote(req: QuoteReq):
    q = build_quote(req.segment, req.num_sites, req.bundle, req.qty, req.current_spend,
                    req.price_mode)
    if req.profile is not None:
        ok, reasons = validate_bundle(Profile.from_dict(req.profile), req.bundle)
        q["eligibility"] = {"ok": ok, "reasons": reasons}
    return q


# ---------- tracker / orders ----------
@app.post("/order")
def create_order(req: OrderReq):
    """Accepting the quote. Eligibility is re-checked and the price recomputed
    SERVER-side - the client's totals are never trusted."""
    profile = _verified_profile(req.gstin, req.profile)
    ok, reasons = validate_bundle(profile, req.bundle)
    if not ok:
        raise HTTPException(422, {"message": "Bundle is not eligible", "reasons": reasons})
    q = build_quote(profile.segment, profile.num_sites, req.bundle, req.qty,
                    req.current_spend, req.price_mode)
    return orders.create_order(req.bundle, q, business_ref=privacy.mask(req.gstin or ""))


@app.get("/order/{order_id}")
def get_order(order_id: str):
    o = orders.get_order(order_id)
    if not o:
        raise HTTPException(404, "order not found")
    return o


@app.post("/order/{order_id}/advance")
def advance_order(order_id: str):
    o = orders.advance(order_id)
    if not o:
        raise HTTPException(404, "order not found")
    return o


# ---------- O4 KYC (all KYC endpoints sit behind the consent gate, O8) ----------
def _specimen_files(applicant: str) -> dict:
    root = os.path.join(config.DATA_DIR, "kyc_documents")
    return {os.path.basename(p).split("_", 1)[1].rsplit(".", 1)[0]: p
            for p in glob.glob(os.path.join(root, f"{applicant}_*.png"))}


@app.get("/kyc/applicants")
def kyc_applicants():
    root = os.path.join(config.DATA_DIR, "kyc_documents")
    ids = sorted({os.path.basename(p).split("_")[0] for p in glob.glob(os.path.join(root, "*.png"))})
    return ids


@app.get("/kyc/validate")
def kyc_one(applicant: str = Query(..., description="specimen id, e.g. K01"),
            typed_gstin: Optional[str] = None,
            x_consent_receipt: Optional[str] = Header(None)):
    require_consent(x_consent_receipt)
    if not re.fullmatch(r"K\d{2}", applicant):
        raise HTTPException(400, "applicant must look like K01")
    present = _specimen_files(applicant)
    if not present:
        raise HTTPException(404, f"no documents for {applicant}")
    return kyc_validate.validate_present(applicant, present, typed_gstin=typed_gstin)


@app.get("/kyc/validate_all")
def kyc_all(x_consent_receipt: Optional[str] = Header(None)):
    require_consent(x_consent_receipt)
    return kyc_validate.validate_all(os.path.join(config.DATA_DIR, "kyc_documents"))


@app.post("/kyc/upload")
async def kyc_upload(gst_certificate: Optional[UploadFile] = File(None),
                     udyam_certificate: Optional[UploadFile] = File(None),
                     signatory_id: Optional[UploadFile] = File(None),
                     address_proof: Optional[UploadFile] = File(None),
                     typed_gstin: Optional[str] = Form(None),
                     typed_udyam: Optional[str] = Form(None),
                     order_id: Optional[str] = Form(None),
                     x_consent_receipt: Optional[str] = Header(None)):
    """Upload the four KYC documents (one multipart field per slot). Images are
    OCR'd from a temp folder and DELETED immediately; only the masked outcome is
    kept (data minimisation). An APPROVE advances the order to 'KYC verified'."""
    require_consent(x_consent_receipt)
    slots = {"gst_certificate": gst_certificate, "udyam_certificate": udyam_certificate,
             "signatory_id": signatory_id, "address_proof": address_proof}
    tmp = tempfile.mkdtemp(prefix="kyc_upload_")
    try:
        present = {}
        for slot, f in slots.items():
            if f is None:
                continue
            ext = os.path.splitext(f.filename or "")[1].lower()
            if ext not in (".png", ".jpg", ".jpeg"):
                raise HTTPException(400, f"{slot}: only PNG/JPG images are accepted")
            dest = os.path.join(tmp, slot + ext)
            data = await f.read()
            if len(data) > 8 * 1024 * 1024:
                raise HTTPException(400, f"{slot}: file too large (max 8 MB)")
            with open(dest, "wb") as out:
                out.write(data)
            present[slot] = dest
        result = kyc_validate.validate_present("UPLOAD", present, typed_gstin, typed_udyam)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)       # raw documents never persist

    if order_id:
        orders.record_kyc(order_id, result["decision"], result.get("gstin_masked"))
    log.info("kyc decision=%s gstin=%s order=%s", result["decision"],
             result.get("gstin_masked"), order_id)
    return result


# ---------- O5 propensity ----------
@app.post("/score")
def score(req: ScoreReq):
    return propensity.score(req.lead)


# ---------- O7 analytics (dashboard) ----------
@app.get("/analytics/summary")
def analytics_summary():
    return analytics.summary()


@app.get("/analytics/leads")
def analytics_leads(limit: int = 50, band: Optional[str] = None):
    return analytics.scored_leads(limit, band)


@app.get("/analytics/retention")
def analytics_retention():
    return analytics.retention()


# ---------- O8 privacy ----------
@app.get("/privacy/consent")
def consent_notice():
    return privacy.consent_notice()


@app.post("/privacy/consent")
def record_consent(business_ref: str = Query(...)):
    return privacy.record_consent(business_ref)


@app.get("/privacy/consent/{receipt_id}")
def get_consent(receipt_id: str):
    r = privacy.get_consent(receipt_id)
    if not r:
        raise HTTPException(404, "receipt not found")
    return r
