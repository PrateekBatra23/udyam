"""FastAPI entry point. Loads data on startup and wires every endpoint from the
spec's endpoint->module map (section 15)."""
import os
import tempfile
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
import db
from data_store import get_store
from rules.eligibility import Profile
from rules.quote import build_quote
from advisor import agent
from advisor.segment import infer_segment
from kyc import validate as kyc_validate, lookups
from tracker import orders
from propensity import score as propensity
import privacy

app = FastAPI(title="Project Udyam Digital API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    get_store()   # load reference CSVs into memory once
    db.init_db()  # create Postgres tables for orders + consent if absent


# ---------- models ----------
class RecommendReq(BaseModel):
    profile: dict
    current_spend: Optional[int] = None
    language: str = "en"


class QuoteReq(BaseModel):
    segment: str
    num_sites: int = 1
    bundle: list[str]
    qty: Optional[dict] = None
    current_spend: Optional[int] = None


class OrderReq(BaseModel):
    bundle: list[str]


class ScoreReq(BaseModel):
    lead: dict


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
    r = lookups.gstin_status(gstin)
    if not r.get("found"):
        raise HTTPException(404, "GSTIN not found")
    return r


@app.get("/udyam/{udyam}")
def udyam(udyam: str):
    r = lookups.udyam_status(udyam)
    if not r.get("found"):
        raise HTTPException(404, "Udyam not found")
    return r


@app.get("/onboard")
def onboard(gstin: str = Query(...), udyam: Optional[str] = None):
    """GSTIN-first autofill + inferred (confirmable) segment."""
    g = get_store().gstin_lookup(gstin)
    if not g:
        raise HTTPException(404, "GSTIN not found in registry")
    u = get_store().udyam_lookup(udyam) if udyam else None
    seg = infer_segment(g, u)
    return {
        "gstin": gstin,
        "legal_name": g.get("legal_name"),
        "trade_name": g.get("trade_name"),
        "constitution": g.get("constitution"),
        "state": g.get("state"),
        "principal_place_of_business": g.get("principal_place_of_business"),
        "status": g.get("status"),
        "inferred_segment": seg,         # {segment, confidence, basis} — confirm in UI
    }


# ---------- O2 advisor ----------
@app.post("/advisor/recommend")
def recommend(req: RecommendReq):
    return agent.recommend(req.profile, req.current_spend, req.language)


# ---------- O3 quote ----------
@app.post("/quote")
def quote(req: QuoteReq):
    return build_quote(req.segment, req.num_sites, req.bundle, req.qty, req.current_spend)


# ---------- O4 KYC ----------
@app.get("/kyc/validate")
def kyc_one(applicant: str = Query(..., description="e.g. K01"),
            typed_gstin: Optional[str] = None):
    root = os.path.join(config.DATA_DIR, "kyc_documents")
    import glob
    present = {os.path.basename(p).split("_", 1)[1].replace(".png", ""): p
               for p in glob.glob(os.path.join(root, f"{applicant}_*.png"))}
    if not present:
        raise HTTPException(404, f"no documents for {applicant}")
    return kyc_validate.validate_present(applicant, present, typed_gstin=typed_gstin)


@app.get("/kyc/validate_all")
def kyc_all():
    root = os.path.join(config.DATA_DIR, "kyc_documents")
    return kyc_validate.validate_all(root)


@app.post("/kyc/upload")
async def kyc_upload(files: list[UploadFile] = File(...),
                     typed_gstin: Optional[str] = None):
    """Upload the 4 docs named <anything>_<doctype>.png (doctype in
    gst_certificate|udyam_certificate|signatory_id|address_proof)."""
    tmp = tempfile.mkdtemp(prefix="kyc_upload_")
    present = {}
    for f in files:
        name = f.filename or "doc.png"
        doctype = name.rsplit("_", 1)[-1].replace(".png", "").lower()
        dest = os.path.join(tmp, name)
        with open(dest, "wb") as out:
            out.write(await f.read())
        present[doctype] = dest
    return kyc_validate.validate_present("UPLOAD", present, typed_gstin=typed_gstin)


# ---------- tracker ----------
@app.post("/order")
def create_order(req: OrderReq):
    return orders.create_order(req.bundle)


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


# ---------- O5 propensity ----------
@app.post("/score")
def score(req: ScoreReq):
    return propensity.score(req.lead)


# ---------- O7 analytics (dashboard) ----------
@app.get("/analytics/summary")
def analytics():
    df = get_store().leads
    if df.empty:
        return {"note": "smb_leads.csv not loaded"}
    n = len(df)
    act = df[df["outcome"] == "Activated"]

    def rate_by(col):
        out = {}
        for k, grp in df.groupby(col):
            a = (grp["outcome"] == "Activated").sum()
            out[str(k)] = {"activated": int(a), "total": int(len(grp)),
                           "rate_pct": round(a / len(grp) * 100, 1)}
        return out

    return {
        "total_leads": n,
        "activation_rate_pct": round(len(act) / n * 100, 1),
        "median_days_to_activation": float(act["days_lead_to_activation"].median()),
        "churn_rate_pct": round((act["churned_within_6_months"] == "Y").mean() * 100, 1),
        "mean_nps": round(act["nps_score"].mean(), 1),
        "by_gstin": rate_by("has_gstin"),
        "by_segment": rate_by("segment"),
        "by_lead_source": rate_by("lead_source"),
        "by_city_tier": rate_by("city_tier"),
        "top_drop_reasons": df[df["drop_reason"].notna()]["drop_reason"]
                              .value_counts().head(8).to_dict(),
    }


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
